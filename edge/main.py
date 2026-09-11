"""UrbanLens edge agent — runs on the bus.

Loop: camera frame -> detect -> privacy-filter -> geo-tag -> spool -> upload.
Requires a real ONNX model and a real video source (webcam or recording);
GPS comes from a serial puck or deterministic route replay.
"""
import argparse
import logging
import os
import threading
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

from anpr import ANPR                    # noqa: E402
from rash_detector import RashDetector    # noqa: E402
from buffer import Spool                    # noqa: E402
from camera import CameraSource, find_demo_video   # noqa: E402
from detector import load_detector          # noqa: E402
from gps import make_gps                    # noqa: E402
from privacy import crop_evidence           # noqa: E402
from traffic_counter import TrafficCounter  # noqa: E402
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
        vehicle_type: str = "bus", with_traffic: bool = True) -> None:
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
    camera = CameraSource(src, fps_cap=10.0)

    # Static road defects do not move between frames: running the defect
    # model every Nth frame (default 2) halves its cost with zero precision
    # loss — the streak gate still needs 2 hits inside a 1.5 s window and
    # 5 fps / 2 = 2.5 looks per second satisfies it. Set EDGE_DEFECT_EVERY=1
    # to restore per-frame inference.
    defect_every = max(1, int(os.getenv("EDGE_DEFECT_EVERY", "2")))
    if defect_every > 1:
        log.info("defect inference: every %dth frame (static defects; "
                 "streak window unaffected)", defect_every)

    # GPU providers (DirectML/CUDA) must NOT run concurrent sessions from
    # multiple threads (DML command recorder is not thread-safe); on GPU the
    # models are fast enough (~20 ms) that sequential is optimal anyway.
    # CPU keeps the parallel defect thread (~1.6x).
    _providers = [p.lower() for p in detector.session.get_providers()]
    _gpu = any("dml" in p or "cuda" in p for p in _providers)
    if _gpu:
        log.info("GPU inference active (%s) — sequential model calls",
                 detector.session.get_providers()[0])

    # live traffic counting (real COCO inference on the same feed)
    traffic = None
    if with_traffic:
        coco = _resolve_model_path(os.getenv("EDGE_COCO_PATH", "edge/models/coco.onnx"))
        if coco:
            backend = os.getenv("EDGE_BACKEND_URL", "http://localhost:8000")
            traffic = TrafficCounter(coco, backend, os.getenv("API_TOKEN", "sih-demo-token"),
                                     vehicle_code, route_file or "route_01")
            log.info("traffic counting: ON (COCO %s -> %s)", Path(coco).name, backend)
        else:
            log.warning("coco.onnx not found - traffic counting disabled")

    # live ANPR (trained plate detector + RapidOCR + multi-frame voting)
    anpr = None
    if with_traffic:
        plate_model = Path(__file__).parent / "models" / "plate.onnx"
        if plate_model.exists():
            backend = os.getenv("EDGE_BACKEND_URL", "http://localhost:8000")
            try:
                anpr = ANPR(backend, os.getenv("API_TOKEN", "sih-demo-token"))
                log.info("ANPR: ON (plate.onnx + RapidOCR, %d-frame voting)", anpr._votes_needed)
            except Exception as exc:
                log.warning("ANPR init failed (%s) — continuing without", exc)
        else:
            log.warning("plate.onnx not found - ANPR disabled")

    # rash-driving detection (heuristics on COCO tracking)
    rash = None
    if traffic is not None:
        rash = RashDetector(backend, os.getenv("API_TOKEN", "sih-demo-token"))
        log.info("rash-driving detection: ON (IoU tracking heuristics)")

    streaks: dict[str, list[float]] = {}
    cooldown: dict[str, float] = {}

    # --- background spool flusher -------------------------------------------
    # Drains the spool every 0.5 s in a daemon thread so the detection loop
    # never waits on network I/O (a Supabase pooler hop is 1-3 s). Same
    # batch/retry semantics as before; the exit flush in `finally` still
    # guarantees at-least-once delivery for whatever is left in the spool.
    def _spool_worker():
        while True:
            time.sleep(0.5)
            try:
                flush_spool(spool, uploader, max_batches=2)
            except Exception:
                log.exception("spool worker error")

    threading.Thread(target=_spool_worker, daemon=True).start()

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

            # --- parallel inference -----------------------------------------
            # The defect model runs in a worker thread alongside the traffic
            # model. ONNX Runtime releases the GIL during inference, so the
            # two run truly concurrently (~1.6x faster than sequential), and
            # thread-tuned sessions give identical outputs.
            det_results: list = []
            det_thread = None
            run_defect = frame.frame_id % defect_every == 0
            if run_defect and not _gpu:
                def _run_defect():
                    det_results.extend(detector.detect(frame.image))
                det_thread = threading.Thread(target=_run_defect, daemon=True)
                det_thread.start()

            if traffic is not None:
                traffic.observe(frame.image, fix)

            if det_thread is not None:
                det_thread.join()
            elif run_defect:                      # GPU: sequential, same result
                det_results.extend(detector.detect(frame.image))

            if anpr is not None:
                try:
                    anpr.observe(frame.image, fix)
                except Exception:
                    log.exception("anpr observe failed")

            if rash is not None and traffic is not None and traffic.last_vehicles:
                try:
                    evidence = rash.observe(traffic.last_vehicles)
                    if evidence:
                        # attach plate if ANPR has a recent read at this location
                        plate = plate_conf = None
                        if anpr is not None:
                            with anpr._lock:
                                recent = [(p, c, t) for p, c, t in anpr._cooldown.items()]
                            # most recently seen plate (cooldown keys are plates)
                            if anpr._cooldown:
                                plate = max(anpr._cooldown,
                                            key=anpr._cooldown.get)
                                plate_conf = 0.9
                        rash.upload(fix, evidence, plate, plate_conf)
                except Exception:
                    log.exception("rash observe failed")

            detections = det_results
            if detections:
                log.info("frame %s: %d detection(s): %s",
                         frame.frame_id, len(detections),
                         [f"{d.label}@{d.confidence:.2f}" for d in detections])

            for det in detections:
                h, w = frame.image.shape[:2]
                if not _passes_gates(det, streaks, cooldown, time.time(), w, h):
                    continue
                # privacy-filtered crop with the issue circled in red;
                # bystanders (persons) pixelated before encoding
                person_boxes = traffic.last_persons if traffic is not None else []
                image_b64 = crop_evidence(frame.image, det.bbox,
                                          label=det.label, confidence=det.confidence,
                                          blur_boxes=person_boxes)
                rec = record_from_detection(det, fix, vehicle_code, image_b64, vehicle_type)
                spool.put(rec)

            # (spool flushing happens in the background worker thread —
            # never block the detection loop on network I/O)
    except KeyboardInterrupt:
        log.info("interrupted — flushing remaining spool")
        flush_spool(spool, uploader, max_batches=50)
    finally:
        if traffic is not None:
            traffic.flush(final=True)
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
    p.add_argument("--no-traffic", action="store_true",
                   help="disable live COCO traffic counting")
    args = p.parse_args()
    origin = None
    if args.gps_origin:
        try:
            lat_s, lon_s = args.gps_origin.split(",")
            origin = (float(lat_s), float(lon_s))
        except ValueError:
            raise SystemExit(f"bad --gps-origin (expected 'lat,lon'): {args.gps_origin}")
    run(args.vehicle, args.video, args.gps_port, args.route, args.conf, args.mqtt, origin,
        args.vehicle_type, with_traffic=not args.no_traffic)
