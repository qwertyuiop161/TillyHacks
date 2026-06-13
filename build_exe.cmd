@echo off
REM Build a standalone Windows EXE for Nexus AI.

echo [1/3] Installing/Updating dependencies...
pip install PySide6 google-generativeai Pillow pymupdf pyinstaller

echo [2/3] Running PyInstaller...
pyinstaller --onefile --windowed --name "NexusAI" --hidden-import fitz --collect-all google.generativeai main.py

if %errorlevel% neq 0 (
    echo [X] Build failed. Check errors above.
    exit /b %errorlevel%
)
echo [3/3] Build complete! Find your app in: dist\NexusAI.exe
