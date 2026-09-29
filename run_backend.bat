@echo off
cd /d "%~dp0backend"
if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate
pip install -q -r requirements.txt
echo Starting API on http://127.0.0.1:8000  (docs at /docs)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
