@echo off
setlocal
cd /d "%~dp0"
if not exist "%APPDATA%\DXWeaver" mkdir "%APPDATA%\DXWeaver"
if not exist "%APPDATA%\DXWeaver\config.json" copy config.pu2bru-wrl.json "%APPDATA%\DXWeaver\config.json" >nul
if exist "%APPDATA%\DXWeaver\.venv\Scripts\activate.bat" call "%APPDATA%\DXWeaver\.venv\Scripts\activate.bat"
dxweaver --config "%APPDATA%\DXWeaver\config.json"
endlocal
