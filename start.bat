@echo off
cd /d "%~dp0"
if not exist .env (
    echo The .env file is missing. Copy .env.example to .env and fill in your API key before running again.
    pause
    exit /b 1
)
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:8000"
.venv\Scripts\python.exe server.py
pause
