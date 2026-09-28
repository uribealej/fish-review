@echo off
setlocal
cd /d "%~dp0"
title Fish Review
if not exist ".venv\Scripts\python.exe" (
    echo The Fish Review Python environment is missing.
    echo Follow the virtual environment setup in README.md first.
    pause
    exit /b 1
)
echo Starting Fish Review in your browser...
echo Keep this window open while using the app. Press Ctrl+C to stop it.
".venv\Scripts\python.exe" -m streamlit run "app.py" --server.address 127.0.0.1 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo Fish Review could not start. See the error above.
    pause
)
