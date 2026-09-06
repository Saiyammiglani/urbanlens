# 🚌 UrbanLens — AI-Powered Mobile Urban Intelligence Platform

**Smart Automation · Edge AI + Cloud Platform**

Public transport buses become mobile sensing platforms: edge AI on the bus detects
road defects, counts traffic, reads number plates and flags rash driving — geo-tagged
and streamed to a cloud backend where dedup, severity scoring, realtime websockets
and a multi-city GIS dashboard turn raw detections into actionable urban intelligence.

> **Real model required.** The edge agent runs only exported ONNX models and refuses
> to start without weights — every event on the dashboard comes from real inference.
> All simulated/seeded data was purged; the live system contains only real events.

---

## Verified Results (measured, not claimed)

| Capability | Model / method | Result |
|---|---|---|
| Road defects (9 classes) | Custom YOLOv8 v3 → ONNX | mAP50 0.669 · open_manhole 0.971 |
| Vehicle/pedestrian counting | YOLOv8 COCO → ONNX | 19/19 vehicles = ground truth on demo route |
| Number-plate detection | YOLOv8 trained on 2,083 Indian plates | mAP50 0.993 · P 0.984 · R 0.987 |
| ANPR read confidence | RapidOCR + 3-frame majority voting | 93–96% on real plates |
| Rash-driving flags | IoU tracking + rule heuristics | 3/3 unit scenarios |
| Detection → dashboard latency | websockets + polling fallback | 1–3 s (target < 5 s) |
| Burst upload reliability | Supabase tx pooler + NullPool | 40/40 POSTs |
| Dashboard UI checks | Puppeteer suite | 83/83 green |
| External API cost | all free tiers | ₹0 |

## Repository Layout

```
.
├── edge/                 # On-bus edge agent (Python)
│   ├── main.py           # Entrypoint — runs all 3 models (~1.6s/frame CPU)
│   ├── camera.py         # Webcam / MJPEG / recorded-video source
│   ├── gps.py            # Serial NMEA GPS + route replay (JSON)
│   ├── detector.py       # Defect detection ONNX (9 classes, v3)
│   ├── traffic_counter.py# Vehicle/pedestrian counting → congestion index
│   ├── anpr.py           # Plate detection + RapidOCR + multi-frame voting
│   ├── rash_detector.py  # IoU tracking → speeding/lane-weaving alerts
│   ├── privacy.py        # On-device blur (faces/bystanders)
│   ├── buffer.py         # Offline store-and-forward spool
│   ├── uploader.py       # HTTPS batch upload (retry) / MQTT
│   └── routes/           # Route replays (Delhi, Mumbai, Bengaluru)
├── backend/              # FastAPI backend (Supabase Postgres or SQLite)
│   └── app/
│       ├── ingest.py     # POST /api/v1/ingest (dedup + severity at source)
│       ├── incidents.py  # CRUD + workflow (new→confirmed→assigned→resolved)
│       ├── traffic.py    # Segments, bottlenecks, OD, delays, ANPR alerts
│       ├── live.py       # Realtime websocket fan-out
│       ├── weather.py    # Open-Meteo (free)
│       ├── aqi.py        # OpenAQ (free)
│       └── routing.py    # Smart routing (avoid defects/congestion)
├── dashboard/            # Vite + React + Leaflet control room
│   └── src/components/   # Live Map, Incidents, Traffic, Analytics,
│                         # Media, Live Cam, FleetStrip, SmartRoute
├── ml/                   # Training pipelines (v1→v3 defect, plate detector)
│   ├── train_v3.py       # Defect model v3 (mAP50 0.669)
│   ├── prepare_plate.py / train_plate.py  # Plate detector (mAP50 0.993)
│   └── export_onnx.py    # PT → ONNX export
└── scripts/              # start_backend.bat / start_demo.ps1 / run_edge.bat
```

## Edge Models (edge/models/)

| File | Purpose | Source |
|---|---|---|
| `model.onnx` | 9-class road-defect detection | trained v3 (ml/train_v3.py) |
| `coco.onnx` | vehicle/pedestrian counting | YOLOv8n COCO export |
| `plate.onnx` | license-plate detection | trained (ml/train_plate.py) |

## Quickstart

```bash
cp .env.example .env        # fill DATABASE_URL (Supabase tx pooler :6543), API_TOKEN

# 1. Backend
scripts/start_backend.bat   # or: uvicorn app.main:app --port 8000

# 2. Dashboard
cd dashboard && npm install && npm run dev   # http://127.0.0.1:5173

# 3. Edge agent (real video + route replay)
scripts/run_edge.bat        # → edge/main.py --vehicle DL01CJ8943 --type bus \
                            #    --video media/route_demo.mp4 --route routes/route_01.json
```

Public demo URLs via Cloudflare quick tunnels (see `scripts/`).

## Data Flow

```
Camera ─► [Edge: 3× ONNX detect → OCR → vote → blur PII → geo-tag]
              │  raw video never leaves the bus
              ▼
      HTTPS POST /api/v1/* (batch, retry, offline spool)
              ▼
      [Backend: dedup (geo+time) → severity → nearest-city → persist]
              ▼
      [Postgres/Supabase] ──realtime──► [Dashboard: map, congestion heat,
                                          alerts, analytics, workflow]
```

## Privacy Model

- Raw video **never leaves the bus** — only detections + small blurred crops.
- Faces/bystanders blurred on-device (`edge/privacy.py`).
- ANPR alerts store plate text + confidence + GPS only; no face imagery retained.
- Browser uses anon key only; server credentials never ship to the client.

## ML Pipeline

See `ml/README.md`. Defect model iterated v1 (0.580) → v3 (0.669) on public
datasets; plate detector trained on 2,083 Indian plate images. Export with
`ml/export_onnx.py`, drop into `edge/models/` — the agent runs real inference
only and errors out if a model is missing.

## Problem-Statement Coverage

Road defects ✅ · traffic density/bottlenecks ✅ · ANPR with confidence/timestamp/
GPS ✅ · rash-driving alerts ✅ · GIS dashboards ✅ · congestion heat maps ✅ ·
OD patterns ✅ · route delays ✅ · edge processing (bandwidth-minimal) ✅ ·
missing road dividers/zebra crossings 🔶 (extension classes) · school-zone
pedestrian alerts 🔶 (geofence rule on live person counts).

## Documentation

Professional documentation set (PDF, repository root):

| Document | Contents |
|---|---|
| `UrbanLens_System_Overview.pdf` | complete system analysis: capabilities, architecture, verified results |
| `UrbanLens_Technical_Architecture.pdf` | layered architecture, tech-stack rationale, measured performance graphs |
| `UrbanLens_PRD.pdf` | goals, personas, MoSCoW scope, functional & non-functional requirements |
| `UrbanLens_Executive_Brief.pdf` | stakeholder summary, KPIs, economics, Q&A positions |
| `UrbanLens_Business_Analysis.pdf` | market sizing, unit economics, TCO, business model, go-to-market |

## License

© 2026 UrbanLens. All rights reserved.
