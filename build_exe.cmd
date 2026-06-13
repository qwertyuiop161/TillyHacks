@echo off
REM Build a standalone Windows EXE for the custom explorer app.
pyinstaller --onefile --windowed main.py
if %errorlevel% neq 0 (
    echo Build failed.
    exit /b %errorlevel%
)
echo Build complete. Find the executable under dist\main.exe
