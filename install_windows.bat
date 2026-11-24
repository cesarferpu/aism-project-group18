@echo off
setlocal
echo === Football Scouting Assistant - Python setup ===
py -m venv .venv
call .venv\Scripts\activate.bat
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
echo.
echo Python dependencies installed.
echo Make sure Ollama is installed and run: ollama pull qwen2.5:1.5b
echo Then run: run_app.bat
pause
