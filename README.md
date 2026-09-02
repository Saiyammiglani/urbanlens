# 🚌 UrbanLens — AI-Powered Mobile Urban Intelligence Platform

**SIH26124 | Bharat Electronics Limited | Smart Automation**

Public transport buses become mobile sensing platforms: edge AI on the bus detects
urban issues (potholes, garbage, illegal parking, waterlogging...), geo-tags them,
and pushes lightweight incident metadata to a cloud backend where a dashboard,
dedup engine, severity scoring, and departmental workflow turn raw detections into
actionable urban intelligence.

> **Real model required.** The edge agent runs only the exported ONNX model
> (YOLOv8) — it refuses to start without weights, so every detection on the
> dashboard comes from real inference, never synthetic data.

---

## Repository Layout

```
.
├── edge/                 # On-bus edge agent (Python)
│   ├── main.py           # Edge agent entrypoint
│   ├── camera.py         # Camera / recorded-video source abstraction
│   ├── gps.py            # GPS reader (serial NMEA) + route replay
│   ├── detector.py       # ONNX inference (real model, no fallback)
│   ├── privacy.py        # On-device anonymization (blur)
│   ├── buffer.py         # Offline store-and-forward queue
│   ├── uploader.py       # MQTT / HTTPS publisher with retry
│   └── replay_route.py   # Simulate a bus driving a route
├── backend/              # FastAPI cloud backend
│   ├── app/
│   │   ├── main.py       # App factory + routes
│   │   ├── models.py     # SQLAlchemy ORM (incidents, updates, vehicles)
│   │   ├── schemas.py    # Pydantic contracts
│   │   ├── ingest.py     # POST /api/v1/ingest
│   │   ├── dedup.py      # Geo+time deduplication engine
│   │   ├── severity.py   # Severity scoring
│   │   ├── incidents.py  # CRUD + workflow state machine
│   │   └── auth.py       # Token auth (demo)
│   ├── mqtt_worker.py    # MQTT consumer → ingest pipeline
│   └── init.sql          # PostGIS bootstrap
├── dashboard/            # Vite + React + Leaflet control room
├── ml/                   # Training/export scaffolding (NOT run now)
├── scripts/
│   ├── simulate_fleet.py # Spin up N virtual buses
│   └── demo.sh           # One-shot end-to-end demo
└── docker-compose.yml    # Postgres (PostGIS) + Mosquitto + backend
```

## Quickstart

### Option A — Docker (recommended)
```bash
cp .env.example .env
docker compose up --build
# dashboard dev server separately (see dashboard/README.md)
```

### Option B — Local, zero external services (SQLite, no MQTT)
```bash
# 1. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. Simulate 3 buses driving routes, pushing detections
cd ../scripts
pip install -r requirements.txt
python simulate_fleet.py --buses 3

# 3. Dashboard
cd ../dashboard
npm install && npm run dev
```

Open http://localhost:5173 — live map, incident feed, heatpoints, workflow.

### One-shot demo
```bash
bash scripts/demo.sh
```

## Data Flow

```
Camera ─► [Edge Agent: detect → blur PII → geo-tag] ─► local buffer
              │ (ONNX YOLOv8 model — required, no fallback)
              ▼
      MQTT (Mosquitto) or HTTPS POST /api/v1/ingest
              ▼
      [Backend: dedup (haversine/H3) → severity score → persist]
              ▼
      [Dashboard: map, heatpoints, feed, assign/resolve workflow]
```

## Privacy Model

- Raw video **never leaves the bus**. Only cropped stills + JSON metadata per incident.
- Faces/plates blurred on-device before any clip is stored (`edge/privacy.py`).
- No biometric data collected or stored anywhere.

## ML Pipeline (scaffolded, not executed)

See `ml/README.md` for the trained v2 model (9 classes, mAP50 0.665). Export
with `ml/export_onnx.py` and drop `model.onnx` at `edge/models/` — the edge
agent runs real inference only and errors out if the model is missing.

## License

For SIH hackathon use.
