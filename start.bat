@echo off
cd /d "%~dp0"
if not exist venv (
    echo Virtual environment 'venv' not found. Creating it...
    python -m venv venv
    call venv\Scripts\activate
    pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
