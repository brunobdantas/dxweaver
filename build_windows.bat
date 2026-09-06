@echo off
setlocal
cd /d "%~dp0"
py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install . pyinstaller
pyinstaller --noconfirm --clean --onefile --name DXWeaver --paths src src\autoft8\__main__.py
echo.
echo Executable created at dist\DXWeaver.exe
where iscc >nul 2>&1
if errorlevel 1 (
  echo Inno Setup not found in PATH. EXE build is complete; run installer\DXWeaver.iss with Inno Setup to create the installer.
) else (
  iscc installer\DXWeaver.iss
  echo Installer created under installer-output\
)
endlocal
