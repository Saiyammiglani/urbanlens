"""Live traffic counting on the bus — real COCO YOLOv8n ONNX inference.

Runs alongside the defect detector on the same camera feed (sampled every
Nth frame — counting doesn't need every frame). Aggregates 10-second
windows of vehicle/person counts, computes a 0-100 congestion index from
the GPS speed drop, and POSTs each window to the backend
(/api/v1/ingest/traffic) where it lands in traffic_segments and pushes to
the dashboard over Supabase Realtime.

All counting is real inference on the real camera stream — no simulation.
"""
import json
import logging
import threading
import time
from pathlib import Path

import requests

log = logging.getLogger("urbanlens.traffic")

# COCO class ids (order in coco_labels.json written by ml/export_onnx.py)
VEHICLE_CLASSES = {"bicycle", "car", "motorcycle", "bus", "truck"}
PERSON_CLASS = "person"

WINDOW_S = 10.0
# The agent loop is already throttled by camera fps_cap + inference time
# (a frame every few seconds on CPU), so counting EVERY processed frame is
# correct — time-based sampling would miss frames in slow loops.
SAMPLE_EVERY = 1
FREE_FLOW_KMH = 40.0      # corridor baseline used for congestion scaling


class TrafficCounter:
    def __init__(self, model_path: str, backend_url: str, api_token: str,
                 vehicle_code: str, route: str, conf_thres: float = 0.30):
        from detector import OnnxDetector  # same ONNX runtime wrapper

        labels = json.loads((Path(model_path).parent / "coco_labels.json").read_text())
        self.det = OnnxDetector(model_path, conf_thres=conf_thres, labels=labels)
        self.backend = backend_url.rstrip("/")
        self.token = api_token
        self.vehicle = vehicle_code
        self.route = route
        self._n = 0
        self.last_vehicles = []   # [(x1,y1,x2,y2,label)] for RashDetector
        self._reset()

    def _reset(self):
        self._t0 = time.time()
        self._counts: dict[str, int] = {}
        self._persons = 0
        self._frames = 0
        self._fixes: list[tuple[float, float, float]] = []  # lat, lon, speed

    def observe(self, frame, fix) -> None:
        """Call once per processed camera frame (after gps.read())."""
        self._n += 1
        self._fixes.append((fix.lat, fix.lon, getattr(fix, "speed_kmh", 0.0)))
        if self._n % SAMPLE_EVERY:
            return
        self._frames += 1
        veh_boxes = []
        for det in self.det.detect(frame):
            if det.label in VEHICLE_CLASSES:
                self._counts[det.label] = self._counts.get(det.label, 0) + 1
                veh_boxes.append((*det.bbox, det.label))
            elif det.label == PERSON_CLASS:
                self._persons += 1
        self.last_vehicles = veh_boxes
        if time.time() - self._t0 >= WINDOW_S:
            self.flush()

    def flush(self, final: bool = False) -> None:
        """Close the window: compute congestion, POST segment to backend.
        Empty windows (nothing seen, no speed change) are skipped — they
        add noise to the heatmap and tell the backend nothing new."""
        if self._frames == 0 and not self._fixes:
            return
        total_veh = sum(self._counts.values())
        if total_veh == 0 and self._persons == 0:
            self._reset()
            return

        # avg GPS position + speed across the window
        lat = sum(f[0] for f in self._fixes) / len(self._fixes)
        lon = sum(f[1] for f in self._fixes) / len(self._fixes)
        gps_speed = sum(f[2] for f in self._fixes) / len(self._fixes) if self._fixes else 0.0

        # congestion index: counted vehicles + speed deficit vs free-flow
        veh_index = min(100, total_veh * 12)
        speed_penalty = max(0.0, 1 - gps_speed / FREE_FLOW_KMH) * 40 if gps_speed > 0 else 0.0
        congestion = min(100, int(veh_index + speed_penalty))
        if self._persons >= 2:
            congestion = min(100, congestion + 20)  # crowded curbside

        payload = {
            "vehicle_code": self.vehicle,
            "route": self.route,
            "lat": round(lat, 6), "lon": round(lon, 6),
            "vehicle_counts": self._counts,
            "total_vehicles": total_veh,
            "persons": self._persons,
            "speed_kmh": round(gps_speed, 1),
            "congestion": congestion,
        }

        def _upload():
            # non-blocking for the detection loop; 2 attempts (Supabase pooler
            # occasionally stalls a cold connection for a few seconds)
            for attempt in (1, 2):
                try:
                    r = requests.post(f"{self.backend}/api/v1/traffic/ingest",
                                      json=payload, headers={"X-API-Token": self.token},
                                      timeout=12)
                    if r.status_code == 200:
                        log.info("traffic window: %d vehicles %s | %d persons | %.0f km/h | congestion %d -> uploaded",
                                 total_veh, self._counts, self._persons, gps_speed, congestion)
                        return
                except requests.RequestException:
                    pass
                time.sleep(1.5)
            log.warning("traffic window upload failed twice (backend will miss this window)")

        threading.Thread(target=_upload, daemon=True).start()
        self._reset()
