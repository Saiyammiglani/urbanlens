# Architecture

```
┌──────────────────────────── BUS (EDGE) ────────────────────────────┐
│  Dashcam/Webcam ─► Detector (ONNX YOLOv8 — required)               │
│        │                                                           │
│        ▼                                                           │
│  Privacy filter (blur/pxlate people, crop evidence JPEG)           │
│        │                                                           │
│  GPS fix (serial NMEA or route replay) + timestamp ──► geo-tag     │
│        │                                                           │
│  Spool (store-and-forward JSONL; survives dead zones)              │
│        │                                                           │
│  Uploader ── MQTT (QoS1) or HTTPS POST /api/v1/ingest              │
└────────────────────────────────────────────────────────────────────┘
                 │
┌──────────────── BACKEND (FastAPI) ─────────────────────────────────┐
│  Ingest: validate → dedup (35 m / 4 h / same-label, haversine)     │
│        → severity score (1..10) → persist (PostGIS / SQLite)       │
│  Workflow state machine + audit trail + dept routing               │
│  MQTT worker bridges Mosquitto → ingest pipeline                   │
└────────────────────────────────────────────────────────────────────┘
                 │  REST (polled live by dashboard)
┌──────────────── DASHBOARD (Vite+React+Leaflet) ────────────────────┐
│  Live map (severity-sized, status-coloured dots), label histogram, │
│  incident queue with Confirm→Assign→Start→Resolve actions          │
└────────────────────────────────────────────────────────────────────┘
```

## Key design decisions

- **Metadata-first**: only small blurred JPEG crops + JSON leave the bus
  (~5–20 KB per incident). Raw video never leaves the vehicle.
- **Real inference only**: the edge agent refuses to start without the trained
  ONNX model — no synthetic/fallback detections ever reach the backend.
- **Dedup at ingestion, not edge**: buses cross paths; only the backend has
  the global view needed to merge "same pothole, three buses".
- **SQLite ↔ PostGIS swap**: same SQLAlchemy models run on a laptop
  (`sqlite:///urbanlens.sqlite3`) or in docker-compose (PostGIS).

## Scaling sketch (for judges)

500 buses × 5 FPS sampling × ~0.3 detections/frame-peak → edge filtering keeps
upload ≈ 1–5 msgs/bus/min. One FastAPI node + Postgres comfortably ingests
>10k msg/min; horizontal scale via more MQTT workers / async workers.
