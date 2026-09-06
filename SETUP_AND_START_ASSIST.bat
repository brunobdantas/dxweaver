@echo off
setlocal
cd /d "%~dp0"
if not exist config.json copy config.example.json config.json >nul
if not exist .venv\Scripts\python.exe (
  echo [Auto FT8] Preparing Python environment...
  py -m venv .venv || goto :error
)
call .venv\Scripts\activate
python -m pip install -q --upgrade pip
pip install -q . || goto :error
echo [Auto FT8] Starting in configured mode. Recommended: mode=assist for first live test.
autoft8 --config config.json
exit /b %errorlevel%
:error
echo.
echo Auto FT8 setup failed. Keep this window open and send the text above for diagnosis.
pause
exit /b 1
