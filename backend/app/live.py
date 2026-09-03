"""Live camera: MJPEG stream with real-time ONNX detection, served to the
dashboard. Optionally ingests gated detections into the incident pipeline
(route-replay GPS) so pings appear on the live map while you watch.
"""
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import settings

router = APIRouter(prefix="/api/v1/live", tags=["live"])

ROOT = Path(__file__).resolve().parents[2]
EDGE_DIR = ROOT / "edge"
MODEL_PATH = EDGE_DIR / "models" / "model.onnx"

import sys as _sys
if str(EDGE_DIR) not in _sys.path:
    _sys.path.insert(0, str(EDGE_DIR))  # edge modules import each other flatly


def _load_edge_module(name: str, filename: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, EDGE_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LiveEngine:
    """Background webcam loop: detect -> annotate -> latest JPEG (+ ingest).

    GPS priority: real device fix (pushed by the dashboard browser via
    /live/gps — Windows location service / Wi-Fi positioning) > route replay.
    """

    DEVICE_FIX_TTL = 15.0  # seconds a browser-pushed fix stays authoritative

    def __init__(self):
        self._lock = threading.Lock()
        self._frame_jpeg: bytes | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.report = True          # push gated detections into the pipeline
        self.vehicle = "MH01BV4521"
        self.vehicle_type = "bus"
        self.detections = 0
        self.fps = 0.0
        self.error: str | None = None
        self._det = None
        self._gps = None            # replay fallback
        self.device_fix = None      # latest browser fix (Fix-shaped dict)
        self.device_fix_ts = 0.0
        self.gps_source = "route"   # "device" | "route"

    def set_device_fix(self, lat: float, lon: float, speed_kmh: float = 0.0, heading: float = 0.0):
        self.device_fix = {"lat": lat, "lon": lon,
                           "speed_kmh": speed_kmh, "heading": heading}
        self.device_fix_ts = time.time()

    def _read_fix(self):
        """Fresh device fix wins; else deterministic route replay."""
        if self.device_fix and (time.time() - self.device_fix_ts) < self.DEVICE_FIX_TTL:
            self.gps_source = "device"
            fix = self.device_fix
            return type("F", (), {"lat": fix["lat"], "lon": fix["lon"],
                                  "speed_kmh": fix["speed_kmh"],
                                  "heading": fix["heading"]})()
        self.gps_source = "route"
        return self._gps.read() if self._gps else None

    # -- lifecycle ---------------------------------------------------------
    def start(self, cam_index: int = 0):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
        import cv2
        detector_mod = _load_edge_module("edge_detector", "detector.py")
        gps_mod = _load_edge_module("edge_gps", "gps.py")
        privacy_mod = _load_edge_module("edge_privacy", "privacy.py")
        main_mod = _load_edge_module("edge_main_aux", "main.py")  # for _passes_gates

        cap = cv2.VideoCapture(cam_index)
        if not cap.isOpened():
            self.error = f"cannot open camera {cam_index}"
            return
        self._stop.clear()
        self.detections = 0
        self.error = None
        self._det = detector_mod.OnnxDetector(MODEL_PATH, conf_thres=0.40)
        self._gps = gps_mod.ReplayGPS(EDGE_DIR / "routes" / "route_02.json")
        gate = main_mod._passes_gates
        streaks: dict = {}
        cooldown: dict = {}

        def loop():
            import cv2 as _cv2
            from .ingest import process_observation
            from .schemas import ObservationIn
            from .database import SessionLocal

            t_prev = time.time()
            fps_ema = 0.0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    self.error = "camera read failed"
                    time.sleep(0.5)
                    continue
                dets = self._det.detect(frame)
                now = time.time()
                h, w = frame.shape[:2]

                # annotate + gate
                confirmed = []
                for d in dets:
                    x1, y1, x2, y2 = d.bbox
                    color = (37, 211, 102)  # green (BGR)
                    if gate(d, streaks, cooldown, now, w, h):
                        confirmed.append(d)
                        color = (0, 165, 255)  # orange = reported
                        self.detections += 1
                    _cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    _cv2.putText(frame, f"{d.label} {d.confidence:.2f}", (x1, max(0, y1 - 6)),
                                 _cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                if confirmed:
                    _cv2.putText(frame, f"REPORTED: {', '.join(d.label for d in confirmed)}",
                                 (10, 30), _cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

                ok2, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok2:
                    with self._lock:
                        self._frame_jpeg = buf.tobytes()

                # refresh GPS source every frame (device fix if fresh, else route)
                fix = self._read_fix()

                # ingest confirmed detections (privacy-filtered evidence)
                if self.report and confirmed:
                    if fix is not None:
                        db = SessionLocal()
                        try:
                            for d in confirmed:
                                img_b64 = privacy_mod.crop_evidence(
                                    frame, d.bbox, label=d.label, confidence=d.confidence)
                                obs = ObservationIn(
                                    vehicle_code=self.vehicle, label=d.label,
                                    vehicle_type=self.vehicle_type,
                                    confidence=round(d.confidence, 4),
                                    lat=round(fix.lat, 6), lon=round(fix.lon, 6),
                                    speed_kmh=round(fix.speed_kmh, 1),
                                    image_b64=img_b64,
                                )
                                process_observation(db, obs)
                            db.commit()
                        finally:
                            db.close()

                dt = time.time() - t_prev
                t_prev = time.time()
                fps_ema = 0.9 * fps_ema + 0.1 / max(dt, 1e-3)
                self.fps = round(fps_ema, 1)
                time.sleep(0.03)  # ~15 fps cap, keep CPU sane

            cap.release()
            with self._lock:
                self._frame_jpeg = None

        self._thread = threading.Thread(target=loop, daemon=True, name="live-cam")
        self._thread.start()

    def stop(self):
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


engine = LiveEngine()


@router.post("/start")
def start(cam: int = 0, vehicle: str = "MH01BV4521", vehicle_type: str = "bus"):
    engine.vehicle = vehicle
    engine.vehicle_type = vehicle_type
    engine.start(cam)
    if engine.error:
        return {"running": False, "error": engine.error}
    return {"running": True, "vehicle": vehicle}


@router.post("/stop")
def stop():
    engine.stop()
    return {"running": False}


@router.post("/report")
def set_report(enabled: bool = True):
    engine.report = bool(enabled)
    return {"report": engine.report}


class GpsIn(BaseModel):
    lat: float
    lon: float
    speed_kmh: float = 0.0
    heading: float = 0.0


@router.post("/gps")
def push_gps(fix: GpsIn):
    """Dashboard browser pushes its real geolocation fix (device location)."""
    engine.set_device_fix(fix.lat, fix.lon, fix.speed_kmh, fix.heading)
    return {"ok": True, "source": "device"}


@router.get("/status")
def status():
    fresh = engine.device_fix and (time.time() - engine.device_fix_ts) < LiveEngine.DEVICE_FIX_TTL
    return {
        "running": engine.running,
        "error": engine.error,
        "fps": engine.fps,
        "detections": engine.detections,
        "report": engine.report,
        "vehicle": engine.vehicle,
        "vehicle_type": engine.vehicle_type,
        "gps_source": engine.gps_source if engine.running else ("device" if fresh else "route"),
        "lat": engine.device_fix["lat"] if fresh else None,
        "lon": engine.device_fix["lon"] if fresh else None,
    }


@router.get("/stream.mjpg")
def stream():
    """MJPEG stream — browsers render it directly in an <img> tag."""
    if not engine.running:
        engine.start(0)
        if engine.error:
            from fastapi import HTTPException
            raise HTTPException(503, engine.error)

    def gen():
        boundary = b"--frame\r\n"
        while not engine._stop.is_set() and engine.running:
            with engine._lock:
                jpg = engine._frame_jpeg
            if jpg:
                yield (boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            time.sleep(1 / 15)

    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
