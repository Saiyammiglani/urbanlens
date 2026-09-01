# API Reference (v1)

Base URL: `http://localhost:8000/api/v1` · Interactive docs: `/docs` (Swagger)

## POST /ingest
Push observations from edge devices. Header: `X-API-Token`.

```json
{
  "observations": [
    {
      "vehicle_code": "BL-BUS-001",
      "label": "pothole",
      "confidence": 0.87,
      "lat": 28.6139, "lon": 77.2330,
      "detected_at": "2026-01-01T10:00:00Z",
      "bbox_area_px": 8400, "speed_kmh": 31.2,
      "image_b64": null
    }
  ]
}
```
Response: `{ "received": 1, "new_incidents": 1, "merged": 0 }`
Repeated detections within ~35 m / 4 h of an open same-label incident are
**merged** (count++, severity recomputed) instead of creating duplicates.

## GET /incidents
Query: `status`, `label`, `min_severity`, `limit`. Returns sorted by severity desc.

## GET /incidents/stats
`{ total, open, resolved, avg_severity, by_label }`

## GET /incidents/{id} · GET /incidents/{id}/updates
Incident detail + full workflow audit trail.

## POST /incidents/{id}/transition
Workflow: `new → confirmed → assigned → in_progress → resolved`
(also `→ rejected` from any open state, `resolved → in_progress` to reopen).
```json
{ "status": "confirmed", "author": "control-room", "note": "", "assigned_dept": null }
```

## MQTT transport (docker mode)
Single-observation JSON messages published to `urbanlens/ingest` are consumed
by the backend worker and run through the same ingest pipeline.
