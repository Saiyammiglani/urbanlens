#!/usr/bin/env bash
# One-shot end-to-end demo: backend -> fleet simulator -> quick API check.
# Usage: bash scripts/demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/4 starting backend (SQLite mode) =="
(cd backend && [ -d .venv ] || python -m venv .venv)
source backend/.venv/Scripts/activate 2>/dev/null || source backend/.venv/bin/activate
pip install -q -r backend/requirements.txt
uvicorn app.main:app --port 8000 &
BACKEND_PID=$!
cd backend 2>/dev/null || true
cd "$(dirname "$0")/../backend" && sleep 3

echo "== 2/4 health check =="
curl -s http://localhost:8000/api/v1/health && echo

echo "== 3/4 simulating fleet for 45 seconds =="
cd ..
python scripts/simulate_fleet.py --buses 4 --minutes 0.75

echo "== 4/4 dashboard data preview =="
curl -s "http://localhost:8000/api/v1/incidents/stats" && echo
echo "Open the dashboard (cd dashboard && npm install && npm run dev) and visit http://localhost:5173"

kill $BACKEND_PID 2>/dev/null || true
