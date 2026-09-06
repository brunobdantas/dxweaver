@echo off
setlocal
cd /d "%~dp0"
if not exist config.json copy config.example.json config.json >nul
if not exist .venv\Scripts\python.exe py -m venv .venv || goto :error
call .venv\Scripts\activate
pip install -q . || goto :error
echo WARNING: AUTOMATIC TRANSMISSION WILL BE ARMED.
echo Press Ctrl+C to stop. The dashboard HALT TX button also disarms automation.
autoft8 --config config.json --arm
exit /b %errorlevel%
:error
echo Auto FT8 startup failed.
pause
exit /b 1
