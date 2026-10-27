@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo   Whispy - build SINGLE Whispy.exe
echo ================================================
echo.

if not exist venv (
    echo [X] Run build.bat first - it creates venv and installs dependencies.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

if not exist whispy.ico (
    echo [1/2] Drawing icon...
    python make_icon.py
)

echo [2/2] Building single-file Whispy.exe (5-15 minutes, file will be 200-350 MB)...
if exist build rmdir /s /q build
if exist dist\Whispy.exe del /q dist\Whispy.exe
pyinstaller --noconfirm --clean --windowed --onefile ^
    --name Whispy ^
    --icon whispy.ico ^
    --add-data "whispy.ico;." ^
    --collect-all customtkinter ^
    --collect-all yt_dlp ^
    --collect-all faster_whisper ^
    --collect-all ctranslate2 ^
    --collect-all av ^
    --collect-all tokenizers ^
    --collect-all huggingface_hub ^
    --collect-all onnxruntime ^
    --collect-submodules nvidia ^
    --hidden-import PIL._tkinter_finder ^
    app.py
if errorlevel 1 (
    echo [X] PyInstaller failed. Send the text above.
    pause
    exit /b 1
)

echo.
echo   Done: dist\Whispy.exe  (one file, give just this)
echo   First start takes 5-15 s (unpacking). Folders "models" and "Transkripty"
echo   are created next to the exe on first run.
echo.
pause
