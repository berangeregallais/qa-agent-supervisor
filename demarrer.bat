@echo off
cd /d "%~dp0"
if not exist .env (
    echo Le fichier .env est manquant. Copie .env.example en .env et renseigne ta cle API avant de relancer.
    pause
    exit /b 1
)
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:8000"
.venv\Scripts\python.exe server.py
pause
