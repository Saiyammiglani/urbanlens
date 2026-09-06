# -*- coding: utf-8 -*-
"""Real COCO vehicle/person counting on demo footage -> traffic segments JSON.

Runs the stock COCO-pretrained YOLOv8n (free, offline) over route_demo.mp4,
counts vehicles by class in 10-second windows, joins them with the route's
GPS trace (from the route JSON), and computes per-segment congestion.

Output: ml/traffic_segments.json  (consumed by backend seed script)
"""
import json
import math
import sys
from pathlib import Path

ML = Path(__file__).parent
EDGE = ML.parent / "edge"


def haversine(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def main():
    import cv2
    from ultralytics import YOLO

    route_file = EDGE / "routes" / "route_01.json"
    pts = json.loads(route_file.read_text())
    if pts and isinstance(pts[0], dict):
        pts = [(p["lat"], p["lon"]) for p in pts]
    print(f"route points: {len(pts)}")

    model = YOLO("yolov8n.pt")  # COCO pretrained - downloads once, then offline
    names = model.names
    vehicle_classes = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    person_class = 0

    vid = cv2.VideoCapture(str(EDGE / "media" / "route_demo.mp4"))
    fps = vid.get(cv2.CAP_PROP_FPS) or 30
    total = int(vid.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = total / fps
    print(f"footage: {total} frames @ {fps:.0f} fps = {dur:.0f}s")

    window = 10.0
    segments = []
    cur = {"t0": 0.0, "counts": {}, "persons": 0, "frames": 0}
    n = 0

    def flush(t_end):
        if cur["frames"] == 0:
            return
        # map time -> route position (assume constant speed along route)
        frac = min(0.999, t_end / dur)
        idx = int(frac * (len(pts) - 1))
        lat, lon = pts[idx]
        nxt = pts[min(idx + 1, len(pts) - 1)]
        # bus speed from GPS spacing across the window
        seg_len = haversine((lat, lon), nxt) * max(1, len(pts) - 1) / max(dur / window, 1)
        speed_kmh = min(60.0, (haversine((lat, lon), nxt) / max(dur / len(pts), 0.1)) * 3.6)
        total_veh = sum(cur["counts"].values())
        # congestion index 0-100: vehicles seen per 10s vs typical free-flow (<3)
        congestion = min(100, int(total_veh * 12))
        if cur["persons"] >= 2:
            congestion = min(100, congestion + 20)
        segments.append({
            "lat": round(lat, 6), "lon": round(lon, 6),
            "t_start": round(cur["t0"], 1), "t_end": round(t_end, 1),
            "vehicle_counts": cur["counts"],
            "total_vehicles": total_veh,
            "persons": cur["persons"],
            "speed_kmh": round(speed_kmh, 1),
            "congestion": congestion,
        })

    while True:
        ok, frame = vid.read()
        if not ok:
            break
        n += 1
        t = n / fps
        if t - cur["t0"] >= window:
            flush(t)
            cur = {"t0": t, "counts": {}, "persons": 0, "frames": 0}
        if n % 15:  # sample ~2 fps
            continue
        cur["frames"] += 1
        res = model(frame, verbose=False, conf=0.35, classes=list(vehicle_classes) + [person_class])[0]
        for b in res.boxes:
            c = int(b.cls[0])
            if c in vehicle_classes:
                name = vehicle_classes[c]
                cur["counts"][name] = cur["counts"].get(name, 0) + 1
            elif c == person_class:
                cur["persons"] += 1
    vid.release()
    flush(dur)

    out = ML / "traffic_segments.json"
    out.write_text(json.dumps({
        "source": "real COCO YOLOv8n inference on route_demo.mp4",
        "window_s": window,
        "segments": segments,
    }, indent=1))
    print(f"\n{len(segments)} segments written to {out.name}")
    for s in segments:
        print(f"  t={s['t_start']:5.0f}s  veh={s['total_vehicles']:3d} {s['vehicle_counts']}  "
              f"persons={s['persons']:2d}  congestion={s['congestion']}")


if __name__ == "__main__":
    sys.exit(main())
