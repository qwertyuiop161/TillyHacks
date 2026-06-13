import os
import re
import shutil
import sys
import time
import zipfile
import json
import subprocess
from pathlib import Path
from threading import Thread
from datetime import datetime

import google.generativeai as genai
from PIL import Image

from PySide6.QtCore import (QDir, QRegularExpression, QSortFilterProxyModel, Qt, QStandardPaths, QTimer, 
                            Signal, QObject, QThread, QSize, QModelIndex)
from PySide6.QtGui import QDesktopServices, QIcon, QFont, QPalette, QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPushButton, QStatusBar, QTextEdit, QTreeView, QFileIconProvider,
                               QVBoxLayout, QWidget, QFileSystemModel, QTableView, QHeaderView,
                               QFileDialog, QInputDialog, QAbstractItemView, QToolButton, QTabWidget,
                               QFrame, QScrollArea, QProgressBar)
from PySide6.QtCore import QUrl

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".svg"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".py", ".js", ".html", ".css"}

# --- LLM CONFIGURATION ---
# Ensure you have 'google-generativeai' installed: pip install google-generativeai
# Set your API Key as an environment variable or paste it here.
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyA0nJGLOEm0i-OvSpjwQpkoKqpw8famp-w"))

def safe_read_text(path: Path, max_bytes=2048) -> str:
    try:
        if path.suffix.lower() == ".pdf":
            import fitz # PyMuPDF
            doc = fitz.open(str(path))
            text = chr(12).join([page.get_text() for page in doc])
            return text[:max_bytes]
        with path.open("r", encoding="utf-8", errors="ignore") as file:
            return file.read(max_bytes)
    except Exception:
        return ""

def get_image_dimensions(path: str) -> tuple:
    """Get image width and height, return (w, h) or None"""
    try:
        img = Image.open(path)
        return img.size
    except:
        return None


class FileWorker(QObject):
    result_ready = Signal(str)
    progress_update = Signal(str)
    
    def _query_llm(self, prompt: str) -> str:
        """Internal helper to get a text response from Gemini"""
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    def open_file(self, path: str):
        """Open a file with default application"""
        try:
            if os.path.isdir(path):
                os.startfile(path)
            else:
                os.startfile(path)
            self.result_ready.emit(f"✅ Opened: {path}")
        except Exception as e:
            self.result_ready.emit(f"❌ Error opening file: {str(e)}")
    
    def rename_file(self, old_path: str, new_path: str):
        """Rename or move a file/folder"""
        try:
            if not os.path.exists(old_path):
                self.result_ready.emit(f"❌ Source not found: {old_path}")
                return
            os.rename(old_path, new_path)
            self.result_ready.emit(f"✅ Renamed:\nFrom: {os.path.basename(old_path)}\nTo: {os.path.basename(new_path)}")
        except Exception as e:
            self.result_ready.emit(f"❌ Rename error: {str(e)}")

    def batch_rename(self, folder: str, pattern: str, replacement: str, extension: str = None):
        """Advanced batch renaming with prefix/suffix/replace"""
        try:
            count = 0
            for filename in os.listdir(folder):
                if extension and not filename.lower().endswith(extension.lower()):
                    continue
                
                new_name = filename.replace(pattern, replacement)
                if new_name != filename:
                    os.rename(os.path.join(folder, filename), os.path.join(folder, new_name))
                    count += 1
            self.result_ready.emit(f"✅ Batch Rename Complete: {count} files updated.")
        except Exception as e:
            self.result_ready.emit(f"❌ Batch error: {str(e)}")

    def archive_files(self, source_paths: list, archive_name: str):
        """Compress files into a ZIP archive"""
        try:
            if not archive_name.endswith(".zip"):
                archive_name += ".zip"
            
            with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in source_paths:
                    zipf.write(file, os.path.basename(file))
            
            self.result_ready.emit(f"📦 Archive created: {os.path.basename(archive_name)}")
        except Exception as e:
            self.result_ready.emit(f"❌ Compression error: {str(e)}")

    def extract_archive(self, archive_path: str):
        """Extract a ZIP archive"""
        try:
            dest = archive_path.replace(".zip", "_extracted")
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                zipf.extractall(dest)
            self.result_ready.emit(f"📂 Extracted to: {os.path.basename(dest)}")
        except Exception as e:
            self.result_ready.emit(f"❌ Extraction error: {str(e)}")

    def find_duplicates(self, folder: str):
        """Find duplicate files based on size and name (basic)"""
        try:
            self.progress_update.emit("🔍 Scanning for duplicates...")
            files = {}
            dupes = []
            for root, _, filenames in os.walk(folder):
                for f in filenames:
                    full_path = os.path.join(root, f)
                    size = os.path.getsize(full_path)
                    key = (f, size)
                    if key in files:
                        dupes.append((full_path, files[key]))
                    else:
                        files[key] = full_path
            
            if not dupes:
                self.result_ready.emit("✨ No duplicates found!")
            else:
                res = "👯 DUPLICATES FOUND:\n" + "\n".join([f"• {d[0]} == {d[1]}" for d in dupes[:20]])
                self.result_ready.emit(res)
        except Exception as e:
            self.result_ready.emit(f"❌ Error: {str(e)}")

    def delete_file(self, path: str):
        """Delete a file or directory"""
        try:
            if not os.path.exists(path):
                self.result_ready.emit(f"❌ Path not found: {path}")
                return
            
            name = os.path.basename(path)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self.result_ready.emit(f"🗑️ Deleted: {name}")
        except Exception as e:
            self.result_ready.emit(f"❌ Delete error: {str(e)}")

    def read_file(self, path: str, lines: int = 50):
        """Read and display file contents"""
        try:
            content = safe_read_text(Path(path), max_bytes=50000)
            lines_list = content.split('\n')[:lines]
            summary = f"📄 FILE CONTENTS: {os.path.basename(path)}\n"
            summary += f"{'='*60}\n\n"
            summary += '\n'.join(lines_list)
            if len(content.split('\n')) > lines:
                summary += f"\n... ({len(content.split(chr(10))) - lines} more lines)"
            self.result_ready.emit(summary)
        except Exception as e:
            self.result_ready.emit(f"❌ Error reading file: {str(e)}")
    
    def ai_summarize_and_rename(self, path: str):
        """Use LLM to read a file, summarize it, and propose a better name"""
        try:
            self.progress_update.emit(f"🧠 AI analyzing content of {os.path.basename(path)}...")
            content = safe_read_text(Path(path), max_bytes=10000)
            
            prompt = (
                f"Analyze this file content and provide: 1. A 1-sentence summary. "
                f"2. A concise, descriptive filename (with the original extension). "
                f"Format as JSON: {{'summary': '...', 'new_name': '...'}}\n\nContent:\n{content}"
            )
            
            res_raw = self._query_llm(prompt)
            # Clean JSON from markdown if present
            res_json = res_raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(res_json)
            
            summary = data.get('summary', 'No summary generated.')
            new_name = data.get('new_name', os.path.basename(path))
            
            old_dir = os.path.dirname(path)
            new_path = os.path.join(old_dir, new_name)
            
            os.rename(path, new_path)
            self.result_ready.emit(f"📝 AI SUMMARY: {summary}\n\n✅ Renamed to: {new_name}")
        except Exception as e:
            self.result_ready.emit(f"❌ AI Analysis error: {str(e)}")

    def find_images_by_size(self, folder: str, min_width: int = 0, min_height: int = 0, 
                           max_width: int = None, max_height: int = None):
        """Find images matching size criteria"""
        try:
            self.progress_update.emit(f"🔍 Scanning images in {folder}...")
            results = []
            checked = 0
            start = time.time()
            
            for root, _, filenames in os.walk(folder):
                for filename in filenames:
                    if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
                        path = os.path.join(root, filename)
                        dims = get_image_dimensions(path)
                        if dims:
                            w, h = dims
                            checked += 1
                            if checked % 20 == 0:
                                self.progress_update.emit(f"📸 Checked {checked} images, found {len(results)}...")
                            
                            w_ok = w >= min_width and (max_width is None or w <= max_width)
                            h_ok = h >= min_height and (max_height is None or h <= max_height)
                            
                            if w_ok and h_ok:
                                results.append((path, w, h))
            
            elapsed = time.time() - start
            summary = f"✨ IMAGE SIZE SEARCH ✨\n\n"
            summary += f"📐 Criteria: {min_width}x{min_height}"
            if max_width or max_height:
                summary += f" to {max_width or '∞'}x{max_height or '∞'}"
            summary += f"\n📁 Location: {folder}\n"
            summary += f"✅ Found: {len(results)} images\n"
            summary += f"📊 Scanned: {checked} images\n"
            summary += f"⏱️  Time: {elapsed:.2f}s\n\n"
            summary += "🖼️  Matches:\n"
            for img_path, w, h in results[:30]:
                summary += f"  {w}x{h} - {img_path}\n"
            if len(results) > 30:
                summary += f"\n... and {len(results)-30} more"
            
            self.result_ready.emit(summary)
        except Exception as e:
            self.result_ready.emit(f"❌ Error: {str(e)}")
    
    def summarize_folder(self, folder: str):
        """Analyze folder contents and sizes"""
        try:
            self.progress_update.emit(f"📊 Analyzing {folder}...")
            stats = {}
            total_size = 0
            count = 0
            
            for root, _, filenames in os.walk(folder):
                for f in filenames:
                    count += 1
                    ext = Path(f).suffix.lower() or "no extension"
                    path = os.path.join(root, f)
                    size = os.path.getsize(path)
                    total_size += size
                    stats[ext] = stats.get(ext, 0) + 1
            
            summary = f"📊 FOLDER SUMMARY: {folder}\n{'='*60}\n"
            summary += f"📁 Total Files: {count}\n"
            summary += f"⚖️ Total Size: {total_size / (1024*1024):.2f} MB\n\n"
            summary += "🗂️  File Types:\n"
            for ext, num in sorted(stats.items(), key=lambda x: x[1], reverse=True)[:10]:
                summary += f"  • {ext}: {num} files\n"
            
            self.result_ready.emit(summary)
        except Exception as e:
            self.result_ready.emit(f"❌ Error: {str(e)}")

    def group_files_by_content(self, folder: str, query: str, mode: str = "text"):
        """
        Analyze file contents and group matches into a new folder.
        mode: 'text' for keyword search, 'image' for visual object search.
        """
        try:
            self.progress_update.emit(f"🧠 AI Analyzing {mode}s for '{query}'...")
            matches = []
            
            # Create destination folder name
            clean_query = re.sub(r'[^\w\s-]', '', query).strip().replace(" ", "_")
            dest_folder = os.path.join(folder, f"AI_Grouped_{clean_query}")
            
            for root, _, filenames in os.walk(folder):
                # Don't recurse into the folder we are creating
                if "AI_Grouped_" in root: continue 
                
                for f in filenames:
                    path = os.path.join(root, f)
                    ext = Path(f).suffix.lower()
                    
                    if mode == "text" and ext in TEXT_EXTENSIONS:
                        content = safe_read_text(Path(path), max_bytes=10000)
                        if query.lower() in content.lower():
                            matches.append(path)
                    
                    elif mode == "image" and ext in IMAGE_EXTENSIONS:
                        # This is where you would call a Vision API (e.g., Gemini Vision or OpenAI)
                        # For this framework, we'll simulate a match if the query is in the filename
                        # or metadata. In a real AI implementation, you'd send the image to a model.
                        if self._check_image_ai_mock(path, query):
                            matches.append(path)

            if not matches:
                self.result_ready.emit(f"🔍 No {mode}s found containing '{query}'.")
                return

            # Move matches
            os.makedirs(dest_folder, exist_ok=True)
            for source in matches:
                dest = os.path.join(dest_folder, os.path.basename(source))
                dest = self._resolve_collision(dest)
                shutil.move(source, dest)
            
            self.result_ready.emit(f"✨ AI GROUPING COMPLETE ✨\n\n"
                                  f"📁 Target: {query}\n"
                                  f"📦 Moved: {len(matches)} files\n"
                                  f"📍 Location: {dest_folder}")
                                  
        except Exception as e:
            self.result_ready.emit(f"❌ Grouping error: {str(e)}")

    def _check_image_ai_mock(self, path: str, query: str) -> bool:
        """
        Placeholder for real Vision AI logic.
        To make this real, install 'google-generativeai' and use a Gemini API key
        to describe the image and check if the 'query' object is present.
        """
        # For now, it matches if the object name is in the filename (basic fallback)
        return query.lower() in os.path.basename(path).lower()

    def find_files_by_name(self, folder: str, pattern: str):
        """Find files matching name pattern/regex"""
        try:
            self.progress_update.emit(f"🔎 Searching for '{pattern}' in {folder}...")
            results = []
            checked = 0
            start = time.time()
            
            for root, _, filenames in os.walk(folder):
                for filename in filenames:
                    checked += 1
                    if checked % 100 == 0:
                        self.progress_update.emit(f"🔎 Checked {checked} files, found {len(results)}...")
                    
                    try:
                        if re.search(pattern, filename, re.IGNORECASE):
                            results.append(os.path.join(root, filename))
                    except:
                        if pattern.lower() in filename.lower():
                            results.append(os.path.join(root, filename))
            
            elapsed = time.time() - start
            summary = f"✨ FILE SEARCH ✨\n\n"
            summary += f"🔍 Pattern: {pattern}\n"
            summary += f"📁 Location: {folder}\n"
            summary += f"✅ Found: {len(results)} files\n"
            summary += f"⏱️  Time: {elapsed:.2f}s\n\n"
            summary += "📄 Matches:\n"
            for path in results[:50]:
                summary += f"  {path}\n"
            if len(results) > 50:
                summary += f"\n... and {len(results)-50} more"
            
            self.result_ready.emit(summary)
        except Exception as e:
            self.result_ready.emit(f"❌ Error: {str(e)}")
    
    def copy_files(self, source_list: list, dest_folder: str):
        """Copy multiple files to destination"""
        try:
            os.makedirs(dest_folder, exist_ok=True)
            self.progress_update.emit(f"📋 Copying {len(source_list)} files...")
            copied = 0
            failed = 0
            start = time.time()
            
            for source in source_list:
                try:
                    dest = os.path.join(dest_folder, os.path.basename(source))
                    dest = self._resolve_collision(dest)
                    shutil.copy2(source, dest)
                    copied += 1
                    if copied % 10 == 0:
                        self.progress_update.emit(f"📋 Copied {copied}/{len(source_list)}...")
                except:
                    failed += 1
            
            elapsed = time.time() - start
            summary = f"✨ COPY COMPLETE ✨\n\n"
            summary += f"✅ Copied: {copied} files\n"
            summary += f"❌ Failed: {failed}\n"
            summary += f"📁 Destination: {dest_folder}\n"
            summary += f"⏱️  Time: {elapsed:.2f}s"
            self.result_ready.emit(summary)
        except Exception as e:
            self.result_ready.emit(f"❌ Error: {str(e)}")
    
    def move_files(self, source_list: list, dest_folder: str):
        """Move multiple files to destination"""
        try:
            os.makedirs(dest_folder, exist_ok=True)
            self.progress_update.emit(f"📦 Moving {len(source_list)} files...")
            moved = 0
            failed = 0
            start = time.time()
            
            for source in source_list:
                try:
                    dest = os.path.join(dest_folder, os.path.basename(source))
                    dest = self._resolve_collision(dest)
                    shutil.move(source, dest)
                    moved += 1
                    if moved % 10 == 0:
                        self.progress_update.emit(f"📦 Moved {moved}/{len(source_list)}...")
                except:
                    failed += 1
            
            elapsed = time.time() - start
            summary = f"✨ MOVE COMPLETE ✨\n\n"
            summary += f"✅ Moved: {moved} files\n"
            summary += f"❌ Failed: {failed}\n"
            summary += f"📁 Destination: {dest_folder}\n"
            summary += f"⏱️  Time: {elapsed:.2f}s"
            self.result_ready.emit(summary)
        except Exception as e:
            self.result_ready.emit(f"❌ Error: {str(e)}")
    
    def _resolve_collision(self, path: str) -> str:
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(f"{base}_{i}{ext}"):
            i += 1
        return f"{base}_{i}{ext}"



class ExplorerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚀 Nexus AI - File Intelligence")
        self.resize(1700, 950)

        self.currentPath = QDir.rootPath()
        self.downloadFolder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        if not self.downloadFolder:
            self.downloadFolder = str(Path.home() / "Downloads")

        self.worker = FileWorker()
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.worker.result_ready.connect(self.on_worker_result)
        self.worker.progress_update.connect(self.on_progress_update)
        self.thread.start()

        self.setupUI()
        self.applyModernStyleSheet()
        self.statusBar().showMessage("Ready | Type your request →")
        self.reloadKnownDownloads()
        self.downloadTimer = QTimer()
        self.downloadTimer.timeout.connect(self.scanDownloads)

    def reloadKnownDownloads(self):
        if os.path.exists(self.downloadFolder):
            self.knownDownloads = set(os.listdir(self.downloadFolder))
        else:
            self.knownDownloads = set()

    def toggleDownloadMonitor(self, checked):
        if checked:
            self.reloadKnownDownloads()
            self.downloadTimer.start(5000)  # Check every 5 seconds
            self.statusBar().showMessage("📥 Download monitoring active")
        else:
            self.downloadTimer.stop()
            self.statusBar().showMessage("📥 Download monitoring stopped")

    def scanDownloads(self):
        if not os.path.exists(self.downloadFolder):
            return
        current_files = set(os.listdir(self.downloadFolder))
        new_files = current_files - self.knownDownloads
        for file_name in new_files:
            path = os.path.join(self.downloadFolder, file_name)
            if file_name.endswith((".crdownload", ".part", ".tmp")) or os.path.isdir(path):
                continue
            if self.autoRenameCheck.isChecked():
                Thread(target=lambda p=path: self.worker.ai_summarize_and_rename(p), daemon=True).start()
        self.knownDownloads = current_files

    def setupUI(self):
        central = QWidget()
        layout = QHBoxLayout(central)

        # Left sidebar - Explorer
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        
        title = QLabel("📁 EXPLORER")
        title.setFont(self._makeFont(size=14, bold=True))
        left_layout.addWidget(title)
        left_layout.addSpacing(10)

        self.fileSystemModel = QFileSystemModel()
        self.iconProvider = QFileIconProvider()
        self.fileSystemModel.setIconProvider(self.iconProvider)
        self.fileSystemModel.setRootPath("")
        self.fileSystemModel.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.treeView = QTreeView()
        self.treeView.setModel(self.fileSystemModel)
        self.treeView.setRootIndex(self.fileSystemModel.index(self.currentPath))
        self.treeView.setHeaderHidden(True)
        self.treeView.clicked.connect(self.onTreeClicked)
        left_layout.addWidget(self.treeView)

        left_frame.setMaximumWidth(320)
        layout.addWidget(left_frame, stretch=1)

        # Right panel
        right_layout = QVBoxLayout()

        # Top control bar
        control_frame = QFrame()
        control_layout = QVBoxLayout(control_frame)
        control_layout.setSpacing(12)

        # Path bar
        path_bar = QHBoxLayout()
        path_label = QLabel("📍")
        path_label.setFont(self._makeFont(size=12))
        self.pathInput = QLineEdit(self.currentPath)
        self.pathInput.setReadOnly(False) # Allow manual path entry
        self.pathInput.setFont(self._makeFont(size=10))
        path_bar.addWidget(path_label)
        path_bar.addWidget(self.pathInput)
        self.upButton = self._makeButton("↑ Up", self.goUp)
        path_bar.addWidget(self.upButton)
        control_layout.addLayout(path_bar)

        # AI command bar
        ai_bar = QHBoxLayout()
        ai_label = QLabel("🤖")
        ai_label.setFont(self._makeFont(size=12))
        self.aiInput = QLineEdit()
        self.aiInput.setFont(self._makeFont(size=12))
        self.aiInput.setPlaceholderText("find images, analyze folders, move files, search text...")
        self.aiInput.returnPressed.connect(self.runAiCommand)
        ai_bar.addWidget(ai_label)
        ai_bar.addWidget(self.aiInput)
        self.aiButton = self._makeButton("✨ Run", self.runAiCommand)
        self.aiButton.setMaximumWidth(90)
        ai_bar.addWidget(self.aiButton)
        control_layout.addLayout(ai_bar)

        # Progress display
        self.progressLabel = QLabel("")
        self.progressLabel.setFont(self._makeFont(size=9))
        self.progressLabel.setStyleSheet("color: #6366f1;")
        control_layout.addWidget(self.progressLabel)

        control_frame.setMaximumHeight(140)
        right_layout.addWidget(control_frame)

        # Main tabs
        self.tabs = QTabWidget()
        self.tabs.setFont(self._makeFont(size=11))

        # Files tab
        files_widget = QWidget()
        files_layout = QVBoxLayout(files_widget)
        
        search_bar = QHBoxLayout()
        search_icon = QLabel("🔍")
        search_icon.setFont(self._makeFont(size=12))
        self.searchInput = QLineEdit()
        self.searchInput.setFont(self._makeFont(size=10))
        self.searchInput.setPlaceholderText("Filter files in this folder...")
        self.searchInput.textChanged.connect(self.applyFilter)
        search_bar.addWidget(search_icon)
        search_bar.addWidget(self.searchInput)
        files_layout.addLayout(search_bar)
        
        self.listProxyModel = QSortFilterProxyModel()
        self.listProxyModel.setSourceModel(self.fileSystemModel)
        self.listProxyModel.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.tableView = QTableView()
        self.tableView.setModel(self.listProxyModel)
        self.tableView.doubleClicked.connect(self.onItemActivated)
        self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tableView.setFont(self._makeFont(size=10))
        files_layout.addWidget(self.tableView)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.openButton = self._makeButton("📂 Open", self.openSelectedItem)
        self.renameButton = self._makeButton("✏️ Rename", self.renameSelectedItem)
        self.deleteButton = self._makeButton("🗑️ Delete", self.deleteSelectedItem)
        self.zipButton = self._makeButton("📦 Archive", self.zipSelectedItems)
        buttons.addWidget(self.openButton)
        buttons.addWidget(self.renameButton)
        buttons.addWidget(self.deleteButton)
        buttons.addStretch()
        files_layout.addLayout(buttons)

        self.tabs.addTab(files_widget, "📂 Files")

        # Results tab
        self.resultsView = QTextEdit()
        self.resultsView.setFont(self._makeFont(size=10, family="Courier New"))
        self.resultsView.setReadOnly(True)
        self.tabs.addTab(self.resultsView, "📊 Results")

        # Settings tab
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_title = QLabel("⚙️ Settings")
        settings_title.setFont(self._makeFont(size=13, bold=True))
        settings_layout.addWidget(settings_title)
        settings_layout.addSpacing(10)
        self.monitorCheck = QCheckBox("📥 Download Manager")
        self.monitorCheck.setFont(self._makeFont(size=11))
        self.monitorCheck.toggled.connect(self.toggleDownloadMonitor)
        settings_layout.addWidget(self.monitorCheck)
        self.autoRenameCheck = QCheckBox("🔄 Auto-Rename Downloads")
        self.autoRenameCheck.setFont(self._makeFont(size=11))
        settings_layout.addWidget(self.autoRenameCheck)
        settings_layout.addStretch()
        self.tabs.addTab(settings_widget, "⚙️ Settings")

        right_layout.addWidget(self.tabs, stretch=1)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        layout.addWidget(right_widget, stretch=4)

        self.setCentralWidget(central)
    
    def _makeFont(self, size=10, bold=False, family="Segoe UI"):
        font = QFont(family, size)
        font.setBold(bold)
        return font
    
    def _makeButton(self, text: str, callback):
        btn = QPushButton(text)
        btn.setFont(self._makeFont(size=10, bold=True))
        btn.clicked.connect(callback)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def applyModernStyleSheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget, QFrame { 
                background: #0f172a; 
                color: #e8ecf1; 
            }
            QLineEdit, QTextEdit {
                background: #1e293b; 
                color: #e8ecf1; 
                border: 1px solid #334155;
                border-radius: 8px; 
                padding: 8px; 
                selection-background-color: #6366f1;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #818cf8;
                background: #0f172a;
                outline: none;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
                color: white; 
                border: none; 
                border-radius: 6px;
                padding: 10px 16px; 
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #818cf8, stop:1 #6366f1);
            }
            QPushButton:pressed { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4338ca, stop:1 #3730a3);
            }
            QTreeView, QTableView {
                background: #1a1f3a; 
                color: #e8ecf1; 
                border: 1px solid #3a4660;
                gridline-color: #1e293b;
                font-size: 10pt;
                border-radius: 8px;
            }
            QTreeView::item:hover, QTableView::item:hover {
                background: #2d3748; 
            }
            QTreeView::item:selected, QTableView::item:selected { 
                background: #6366f1; 
                color: white; 
            }
            QHeaderView::section { 
                background: #232d45; 
                color: #cbd5e1; 
                padding: 6px; 
                border: none;
            }
            QLabel { 
                color: #cbd5e1; 
            }
            QTabBar::tab { 
                background: #1e293b; 
                color: #cbd5e1; 
                padding: 10px 20px; 
                margin: 2px; 
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                min-width: 80px;
            }
            QTabBar::tab:selected { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
                color: white; 
            }
            QCheckBox { 
                color: #e8ecf1; 
                font-size: 10pt;
            }
            QCheckBox::indicator { 
                width: 18px; 
                height: 18px; 
                border: 2px solid #4f46e5;
                border-radius: 3px;
                background: #1a1f3a;
            }
            QCheckBox::indicator:checked {
                background: #6366f1;
            }
            QStatusBar {
                background: #0f172a;
                color: #cbd5e1;
                border-top: 1px solid #3a4660;
            }
        """)

    def on_progress_update(self, message: str):
        self.progressLabel.setText(message)
        self.statusBar().showMessage(message)

    def on_worker_result(self, result: str):
        self.resultsView.setPlainText(result)
        self.tabs.setCurrentIndex(1)
        self.progressLabel.setText("✓ Complete")
        self.statusBar().showMessage("✓ Done")
        self.aiButton.setEnabled(True)

    def onTreeClicked(self, index):
        self.currentPath = self.fileSystemModel.filePath(index)
        self.updateListRoot(index)
        self.pathInput.setText(self.currentPath)
        self.statusBar().showMessage(f"📂 {self.currentPath}")

    def updateListRoot(self, sourceIndex):
        proxyIndex = self.listProxyModel.mapFromSource(sourceIndex)
        self.tableView.setRootIndex(proxyIndex if proxyIndex.isValid() else 
                                     self.listProxyModel.mapFromSource(self.fileSystemModel.index(self.currentPath)))

    def applyFilter(self, text: str):
        regexp = QRegularExpression(text)
        self.listProxyModel.setFilterRegularExpression(regexp)

    def onItemActivated(self, proxyIndex):
        sourceIndex = self.listProxyModel.mapToSource(proxyIndex)
        path = self.fileSystemModel.filePath(sourceIndex)
        if os.path.isdir(path):
            self.currentPath = path
            self.updateListRoot(sourceIndex)
            self.pathInput.setText(self.currentPath)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def openSelectedItem(self):
        proxyIndex = self.tableView.currentIndex()
        if proxyIndex.isValid():
            self.onItemActivated(proxyIndex)

    def renameSelectedItem(self):
        proxyIndex = self.tableView.currentIndex()
        if not proxyIndex.isValid():
            return
        sourceIndex = self.listProxyModel.mapToSource(proxyIndex)
        path = self.fileSystemModel.filePath(sourceIndex)
        oldName = os.path.basename(path)
        newName, ok = QFileDialog.getSaveFileName(self, "Rename", os.path.join(os.path.dirname(path), oldName))
        if ok and newName:
            try:
                os.rename(path, newName)
                self.fileSystemModel.refresh(self.fileSystemModel.index(os.path.dirname(path)))
                self.statusBar().showMessage(f"✏️ Renamed to {os.path.basename(newName)}")
            except Exception as e:
                self.statusBar().showMessage(f"❌ {str(e)}")

    def zipSelectedItems(self):
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            return
        
        paths = [self.fileSystemModel.filePath(self.listProxyModel.mapToSource(idx)) for idx in selection]
        archive_name, ok = QInputDialog.getText(self, "Archive", "Archive name:")
        
        if ok and archive_name:
            archive_path = os.path.join(self.currentPath, archive_name)
            Thread(target=lambda: self.worker.archive_files(paths, archive_path), daemon=True).start()

    def deleteSelectedItem(self):
        proxyIndex = self.tableView.currentIndex()
        if not proxyIndex.isValid():
            return
        sourceIndex = self.listProxyModel.mapToSource(proxyIndex)
        path = self.fileSystemModel.filePath(sourceIndex)
        reply = QMessageBox.question(self, "Delete", f"Delete {os.path.basename(path)}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.fileSystemModel.refresh(self.fileSystemModel.index(os.path.dirname(path)))
                self.statusBar().showMessage(f"🗑️ Deleted")
            except Exception as e:
                self.statusBar().showMessage(f"❌ {str(e)}")

    def goUp(self):
        parent = os.path.dirname(self.currentPath.rstrip(os.sep))
        if parent and os.path.isdir(parent):
            self.currentPath = parent
            self.updateListRoot(self.fileSystemModel.index(self.currentPath))
            self.pathInput.setText(self.currentPath)
            self.statusBar().showMessage(f"📂 {self.currentPath}")

    def runAiCommand(self):
        command = self.aiInput.text().strip()
        if not command:
            return
        
        self.progressLabel.setText("⏳ Processing command...")
        self.statusBar().showMessage("Processing...")
        self.aiButton.setEnabled(False)
        
        def run_llm_logic():
            try:
                files = os.listdir(self.currentPath)
                context = f"Current Path: {self.currentPath}\nFiles in directory: {files}"
                
                system_prompt = (
                    "You are a World-Class File Engineering AI. Map user intent to specific tool calls.\n"
                    "TOOLS:\n"
                    "- open_file(path)\n"
                    "- read_file(path)\n"
                    "- rename_file(old_path, new_path)\n"
                    "- delete_file(path)\n"
                    "- archive_files(source_paths, archive_name)\n"
                    "- extract_archive(archive_path)\n"
                    "- summarize_folder(folder_path)\n"
                    "- find_duplicates(folder_path)\n"
                    "- find_files_by_name(folder_path, regex_pattern)\n"
                    "- ai_summarize_and_rename(path) -- USE THIS for reading content and renaming based on summary.\n"
                    "- group_files_by_content(folder, query, mode='text'|'image')\n"
                    "- copy_files(source_list, dest_folder)\n"
                    "- move_files(source_list, dest_folder)\n"
                    "- find_images_by_size(folder, min_width, min_height, max_width, max_height)\n\n"
                    "RULES:\n"
                    "1. Always use absolute paths. Join current path with filenames.\n"
                    "2. Return ONLY a JSON list of actions. No conversational text.\n"
                    "Example: [{\"func\": \"rename_file\", \"args\": [\"C:/old.txt\", \"C:/new.txt\"]}]"
                )
                
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(f"{system_prompt}\n\nCONTEXT:\n{context}\n\nUSER REQUEST: {command}")
                
                raw_text = response.text.replace("```json", "").replace("```", "").strip()
                actions = json.loads(raw_text)
                
                if not actions:
                    self.on_worker_result("🤖 I couldn't map that request to a specific action.")
                    return

                for action in actions:
                    func_name = action.get("func")
                    args = action.get("args", [])
                    if hasattr(self.worker, func_name):
                        method = getattr(self.worker, func_name)
                        method(*args)
                    else:
                        self.on_worker_result(f"❌ AI suggested a tool I don't have: {func_name}")
            
            except Exception as e:
                self.on_worker_result(f"❌ AI Logic Error: {str(e)}")
                self.aiButton.setEnabled(True)

        Thread(target=run_llm_logic, daemon=True).start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExplorerWindow()
    window.show()
    sys.exit(app.exec())