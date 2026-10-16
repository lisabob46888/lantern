#!/bin/sh
# Start Lantern: backend (serves the built frontend) on http://localhost:8910
# Dev mode with hot reload: `./run.sh dev` (frontend on http://localhost:5899)
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  uv venv backend/.venv --python 3.12 && uv pip install -p backend/.venv/bin/python -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then (cd frontend && npm install); fi
if [ "$1" = "dev" ]; then
  (cd backend && .venv/bin/python -m uvicorn app.main:app --port 8910 --reload) &
  cd frontend && npm run dev
else
  (cd frontend && npm run build)
  cd backend && exec .venv/bin/python -m uvicorn app.main:app --port 8910
fi
