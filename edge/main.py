"""UrbanLens edge agent — runs on the bus.

Loop: camera frame -> detect -> privacy-filter -> geo-tag -> spool -> upload.
Requires a real ONNX model and a real video source (webcam or recording);
GPS comes from a serial puck or deterministic route replay.
"""
import argparse
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ROOT = Path(__file__).resolve().parents[1]


def _resolve_model_path(raw: str | None) -> str | None:
    """Resolve EDGE_MODEL_PATH relative to project root (not CWD)."""
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return str(p)
    cand = ROOT / raw
    if cand.exists():
        return str(cand)
    return str(p) if p.exists() else None

from buffer import Spool                    # noqa: E402
from camera import CameraSource, find_demo_video   # noqa: E402
from detector import load_detector          # noqa: E402
from gps import make_gps                    # noqa: E402
from privacy import crop_evidence           # noqa: E402
from uploader import HTTPSUploader, MQTTUploader, make_uploader, record_from_detection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("urbanlens.edge")


def flush_spool(spool: Spool, uploader, max_batches: int = 5) -> None:
    for _ in range(max_batches):
        records = spool.drain()
        if not records:
            return
        if uploader.send(records):
            log.info("uploaded %d observations (spool=%d)", len(records), spool.size())
        else:
            # put them back at the end of the spool and retry later
            for rec in records:
                spool.put(rec)
            log.warning("upload failed, re-queued %d records", len(records))
            return


# --- detection quality gates (tuned on real footage) ------------------------
# Model confidence floor per class. Measured on street footage: real garbage
# dumps fire at 0.70-0.93 while leaves/roadside clutter fire at 0.40-0.62;
# real potholes at 0.66-0.84. Gates keep the real objects, drop the noise.
CLASS_MIN_CONF = {
    "garbage_dump": 0.78,  # leaves/roadside litter fire up to ~0.76; real dumps 0.8-0.95
    "pothole": 0.60,
}
DEFAULT_MIN_CONF = 0.55

# An object must be seen at least this many times within this window before
# it is reported — single-frame blips (leaves, shadows, reflections) never
# pass, while a real roadside object stays in view for several seconds.
# Exception: a single sighting at VERY high confidence is real (leaves and
# clutter sit at 0.4-0.6; genuine dumps fire at 0.7-0.95).
STREAK_NEEDED = 2
STREAK_WINDOW_S = 1.5
SINGLE_HIT_CONF = 0.75

# After reporting a label, stay quiet on it for this long. The backend's
# spatial dedup would merge repeats anyway; this keeps the upload stream lean.
COOLDOWN_S = 4.0


def _passes_gates(det, streaks, cooldown, now, frame_w, frame_h) -> bool:
    """Confidence gate + recent-sighting streak + per-label cooldown."""
    min_conf = CLASS_MIN_CONF.get(det.label, DEFAULT_MIN_CONF)
    if det.confidence < min_conf:
        return False

    if det.confidence >= SINGLE_HIT_CONF:
        confirmed = True
    else:
        # recent hits for this label inside the sliding window (motion-tolerant:
        # a street object shifts a lot between processed frames, so we count
        # sightings in time rather than requiring a static bbox position)
        times = [t for t in streaks.get(det.label, []) if now - t <= STREAK_WINDOW_S]
        times.append(now)
        streaks[det.label] = times
        confirmed = len(times) >= STREAK_NEEDED

    if not confirmed:
        return False
    if now - cooldown.get(det.label, 0.0) < COOLDOWN_S:
        return False
    cooldown[det.label] = now
    streaks[det.label] = []
    return True


def run(vehicle_code: str, video_source: str | None, gps_port: str | None,
        route_file: str | None, conf_thres: float, use_mqtt: bool,
        gps_origin: tuple[float, float] | None = None,
        vehicle_type: str = "bus") -> None:
    # --- wire components -----------------------------------------------------
    detector = load_detector(_resolve_model_path(os.getenv("EDGE_MODEL_PATH")), conf_thres)
    gps = make_gps(gps_port, route_file, origin=gps_origin)

    if use_mqtt and os.getenv("MQTT_HOST"):
        uploader = MQTTUploader(os.getenv("MQTT_HOST"), int(os.getenv("MQTT_PORT", "1883")),
                                os.getenv("MQTT_TOPIC", "urbanlens/ingest"))
    else:
        uploader = HTTPSUploader(os.getenv("EDGE_BACKEND_URL", "http://localhost:8000"),
                                 os.getenv("API_TOKEN", "sih-demo-token"))

    spool = Spool()
    src = video_source or find_demo_video()
    if src is None:
        raise SystemExit(
            "no video source: pass --video <file-or-webcam-index>, or drop an "
            ".mp4 into edge/media/ (real footage only — no synthetic frames)"
        )
    log.info("video source: %s | vehicle: %s", src, vehicle_code)
    camera = CameraSource(src, fps_cap=5.0)

    streaks: dict[str, list[float]] = {}
    cooldown: dict[str, float] = {}

    # --- main loop ------------------------------------------------------------
    try:
        while True:
            frame = camera.read()
            if frame is None:
                log.info("video source ended — looping complete, stopping agent")
                break

            fix = gps.read()
            if fix is None:
                continue  # no GPS fix; never geo-tag a detection blindly

            detections = detector.detect(frame.image)
            if detections:
                log.info("frame %s: %d detection(s): %s",
                         frame.frame_id, len(detections),
                         [f"{d.label}@{d.confidence:.2f}" for d in detections])

            for det in detections:
                h, w = frame.image.shape[:2]
                if not _passes_gates(det, streaks, cooldown, time.time(), w, h):
                    continue
                # privacy-filtered crop with the issue circled in red
                image_b64 = crop_evidence(frame.image, det.bbox,
                                          label=det.label, confidence=det.confidence)
                rec = record_from_detection(det, fix, vehicle_code, image_b64, vehicle_type)
                spool.put(rec)

            # opportunistically drain the spool every loop (~each frame)
            flush_spool(spool, uploader, max_batches=2)
            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("interrupted — flushing remaining spool")
        flush_spool(spool, uploader, max_batches=50)
    finally:
        camera.release()
        if hasattr(uploader, "close"):
            uploader.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="UrbanLens edge agent")
    p.add_argument("--vehicle", default="BL-BUS-001")
    p.add_argument("--type", dest="vehicle_type", default="bus",
                   help="vehicle type: bus|garbage_truck|ambulance|tanker|municipal_car|police_car|other")
    p.add_argument("--video", default=None, help="path to recorded route video (else webcam/mock)")
    p.add_argument("--gps-port", default=None, help="serial port of GPS puck (else route replay)")
    p.add_argument("--route", default=None, help="route JSON for GPS replay")
    p.add_argument("--gps-origin", default=None,
                   help="'lat,lon' of the device — route is translated to start here")
    p.add_argument("--conf", type=float, default=float(os.getenv("EDGE_CONF_THRESHOLD", "0.45")))
    p.add_argument("--mqtt", action="store_true", help="use MQTT instead of HTTPS")
    args = p.parse_args()
    origin = None
    if args.gps_origin:
        try:
            lat_s, lon_s = args.gps_origin.split(",")
            origin = (float(lat_s), float(lon_s))
        except ValueError:
            raise SystemExit(f"bad --gps-origin (expected 'lat,lon'): {args.gps_origin}")
    run(args.vehicle, args.video, args.gps_port, args.route, args.conf, args.mqtt, origin,
        args.vehicle_type)
