@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo   Whispy - build .exe
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found. Install Python 3.10-3.12 from python.org and tick "Add to PATH".
    pause
    exit /b 1
)

if not exist venv (
    echo [1/5] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [X] Could not create venv.
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat

echo [2/5] Installing dependencies (this can take several minutes)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Dependency install failed. Send the text above.
    pause
    exit /b 1
)

echo.
set GPU=N
set /p GPU="NVIDIA GPU present? [y/N]: "
if /i "%GPU%"=="y" (
    echo       Installing CUDA libraries...
    pip install -r requirements-gpu.txt
    if errorlevel 1 echo [!] CUDA libs failed to install - app will run on CPU.
)

echo [3/5] Drawing icon...
python make_icon.py
if errorlevel 1 (
    echo [X] Icon failed.
    pause
    exit /b 1
)

echo [4/5] Building Whispy.exe (3-10 minutes)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm --clean --windowed --onedir ^
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

echo [5/5] Done!
echo.
echo   App: dist\Whispy\Whispy.exe
echo   You can move the whole dist\Whispy folder anywhere.
echo   Folders "Transkripty" and "models" appear next to the exe on first run.
echo.
pause
