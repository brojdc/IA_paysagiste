@echo off
title IA Paysagiste — API (port 8000)
cd /d "%~dp0"
echo Demarrage de l'API sur http://127.0.0.1:8000
echo Docs : http://127.0.0.1:8000/docs
echo (Ctrl+C pour arreter)
echo.
python run_api.py
if %errorlevel% neq 0 (
    echo.
    echo ERREUR : verifiez que les dependances sont installees (pip install -r requirements.txt)
    pause
)
