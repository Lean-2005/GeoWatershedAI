#!/usr/bin/env bash
# Start the GeoWatershed AI backend (FastAPI + Uvicorn).
set -e
cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Starting API on http://127.0.0.1:8000  (docs at /docs)"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
