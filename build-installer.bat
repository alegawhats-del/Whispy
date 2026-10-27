@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo   Whispy - build installer (Inno Setup)
echo ================================================
echo.

if not exist dist\Whispy\Whispy.exe (
    echo [X] dist\Whispy\Whispy.exe not found. Run build.bat first.
    pause
    exit /b 1
)

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
    echo [X] Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php and run again.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
for /f "delims=" %%v in ('python -c "import re;print(re.search(r'APP_VERSION = \"(.*?)\"',open('app.py',encoding='utf-8').read()).group(1))"') do set VER=%%v
echo Version from app.py: %VER%

echo installed> installed.flag
if not exist whispy.ico python make_icon.py

echo Compiling installer...
"%ISCC%" /Q /DAppVersion=%VER% installer.iss
if errorlevel 1 (
    echo [X] Inno Setup failed. Send the text above.
    pause
    exit /b 1
)
del installed.flag

echo.
echo   Done: installer_out\Whispy-Setup-%VER%.exe
echo.
echo   To publish an update:
echo     1. Upload installer_out\Whispy-Setup-%VER%.exe (and dist\Whispy.exe if you also ship portable)
echo     2. Edit version.json: "version": "%VER%", links, notes
echo     3. Users get a prompt on next start or via Help - Check for updates
echo.
pause
