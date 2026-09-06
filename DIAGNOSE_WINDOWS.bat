@echo off
setlocal
cd /d "%~dp0"
if not exist config.json copy config.example.json config.json >nul
if not exist .venv\Scripts\python.exe py -m venv .venv || goto :error
call .venv\Scripts\activate
pip install -q . || goto :error
autoft8 --config config.json --self-test
pause
exit /b %errorlevel%
:error
echo Auto FT8 diagnostic setup failed.
pause
exit /b 1
