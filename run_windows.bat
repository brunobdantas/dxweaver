@echo off
if not exist config.json copy config.example.json config.json >nul
python -m autoft8 --config config.json
