@echo off
cd /d "%~dp0"
if not exist venv (
    echo Run build.bat first - it installs the dependencies.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
python app.py
