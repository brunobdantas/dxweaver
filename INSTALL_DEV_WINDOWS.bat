@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Python 3.10+ is required for this development installer.
  echo For the normal end-user setup use DXWeaver-0.3.0-Setup.exe from the GitHub build.
  pause
  exit /b 1
)
if not exist "%APPDATA%\DXWeaver" mkdir "%APPDATA%\DXWeaver"
if not exist "%APPDATA%\DXWeaver\config.json" copy config.example.json "%APPDATA%\DXWeaver\config.json" >nul
py -m venv "%APPDATA%\DXWeaver\.venv"
call "%APPDATA%\DXWeaver\.venv\Scripts\activate"
python -m pip install --upgrade pip
pip install "%~dp0"
set TARGET=%APPDATA%\DXWeaver\Start-DXWeaver.cmd
>"%TARGET%" echo @echo off
>>"%TARGET%" echo call "%%APPDATA%%\DXWeaver\.venv\Scripts\activate.bat"
>>"%TARGET%" echo dxweaver --config "%%APPDATA%%\DXWeaver\config.json"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\DXWeaver.lnk'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%APPDATA%\DXWeaver'; $s.Save()"
echo.
echo DXWeaver installed for this user. A desktop shortcut was created.
pause
