# -*- coding: utf-8 -*-
"""Seed traffic intelligence tables.

Combines:
  - REAL COCO vehicle/person counts from ml/traffic_segments.json (actual
    inference on route_demo.mp4) — kept as today's live segments
  - A simulated full fleet day across all routes/cities with realistic
    time-of-day congestion curves (morning + evening peaks)
  - Simulated ANPR / rash-driving / school-zone pedestrian alerts

Run:  python seed_traffic.py [--fresh]
"""
import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).parent
import sys
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import TrafficAlert, TrafficSegment  # noqa: E402

random.seed(42)

ROUTES = {
    "Delhi": ["route_01", "route_02"],
    "Mumbai": ["route_mumbai"],
    "Bengaluru": ["route_bengaluru"],
}
ROUTE_NAMES = {
    "route_01": "Route 101 · Connaught Place → Laxmi Nagar",
    "route_02": "Route 102 · Karol Bagh → ITO",
    "route_mumbai": "Route 201 · Andheri → Bandra",
    "route_bengaluru": "Route 301 · Silk Board → KR Puram",
}

# congestion multiplier by hour (two peaks)
HOUR_CURVE = {
    6: 0.35, 7: 0.65, 8: 0.95, 9: 1.0, 10: 0.75, 11: 0.6,
    12: 0.65, 13: 0.6, 14: 0.55, 15: 0.6, 16: 0.7, 17: 0.85,
    18: 0.95, 19: 1.0, 20: 0.8, 21: 0.55, 22: 0.35,
}

PLATES = [
    ("DL 8C AB 1204", 0.94, "car"), ("HR 26 DK 8842", 0.89, "truck"),
    ("DL 3C AX 9071", 0.92, "car"), ("UP 16 CT 5513", 0.86, "bus"),
    ("DL 9C AF 3347", 0.91, "car"), ("MH 02 GH 7721", 0.88, "car"),
    ("DL 1C BZ 4590", 0.95, "truck"), ("KA 05 MN 2108", 0.87, "car"),
]


def load_routes():
    routes = {}
    for f in (BACKEND.parent / "edge" / "routes").glob("*.json"):
        data = json.loads(f.read_text())
        if isinstance(data, list) and data:
            routes[f.stem] = [(p["lat"], p["lon"]) for p in data]
    return routes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="clear traffic tables first")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    if args.fresh:
        db.query(TrafficSegment).delete()
        db.query(TrafficAlert).delete()
        db.commit()
        print("cleared traffic tables")

    geo = load_routes()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # ---- 1. real COCO counting output as live segments ----
    real = json.loads((BACKEND.parent / "ml" / "traffic_segments.json").read_text())
    n_real = 0
    now = datetime.now(timezone.utc)
    for seg in real["segments"]:
        if seg["total_vehicles"] == 0 and seg["persons"] == 0:
            continue
        db.add(TrafficSegment(
            city="Delhi", route=ROUTE_NAMES["route_01"],
            lat=seg["lat"], lon=seg["lon"],
            vehicle_counts=json.dumps(seg["vehicle_counts"]),
            total_vehicles=seg["total_vehicles"], persons=seg["persons"],
            speed_kmh=seg["speed_kmh"], congestion=seg["congestion"],
            hour=now.hour, recorded_at=now,
        ))
        n_real += 1
    print(f"real segments: {n_real}")

    # ---- 2. simulated fleet day ----
    n_sim = 0
    for city, rts in ROUTES.items():
        for rkey in rts:
            pts = geo.get(rkey)
            if not pts:
                continue
            for hour, curve in HOUR_CURVE.items():
                # 2 sampled windows per hour
                for w in range(2):
                    idx = random.randrange(0, len(pts))
                    lat, lon = pts[idx]
                    base = random.uniform(6, 16)
                    total = int(base * curve + random.uniform(0, 4))
                    counts = {}
                    for cls, share in [("car", 0.5), ("motorcycle", 0.22),
                                        ("auto", 0.12), ("bus", 0.09),
                                        ("truck", 0.04), ("bicycle", 0.03)]:
                        c = int(total * share * random.uniform(0.7, 1.3))
                        if c:
                            counts[cls] = c
                    speed = max(6.0, 42 - curve * 30 + random.uniform(-4, 4))
                    cong = min(100, int(curve * 88 + random.uniform(-6, 8)))
                    db.add(TrafficSegment(
                        city=city, route=ROUTE_NAMES[rkey],
                        lat=lat + random.uniform(-0.004, 0.004),
                        lon=lon + random.uniform(-0.004, 0.004),
                        vehicle_counts=json.dumps(counts),
                        total_vehicles=sum(counts.values()),
                        persons=random.randint(0, 6) if curve > 0.8 else random.randint(0, 2),
                        speed_kmh=round(speed, 1), congestion=cong, hour=hour,
                        recorded_at=today + timedelta(hours=hour, minutes=w * 30),
                    ))
                    n_sim += 1
    print(f"simulated segments: {n_sim}")

    # ---- 3. alerts: ANPR / rash driving / school zones ----
    n_alert = 0
    alert_specs = [
        ("rash_driving", "Route 101 · Connaught Place → Laxmi Nagar", "Delhi",
         "Lane weaving at 68 km/h in 30-zone; close cut-in at 0.9 s headway"),
        ("anpr", "Route 102 · Karol Bagh → ITO", "Delhi",
         "Vehicle ran red light at ITO junction; plate captured from front camera"),
        ("rash_driving", "Route 201 · Andheri → Bandra", "Mumbai",
         "Overtake on left at 74 km/h; near-miss with 2-wheeler"),
        ("anpr", "Route 301 · Silk Board → KR Puram", "Bengaluru",
         "Hit-and-run minor scrape with parked car; plate + timestamp + GPS secured"),
        ("school_zone", "Route 102 · Karol Bagh → ITO", "Delhi",
         "School children crossing at unmarked stretch near Bal Bharati; 9 pedestrians, 2 min before bell"),
        ("school_zone", "Route 301 · Silk Board → KR Puram", "Bengaluru",
         "Children alighting from auto at Silk Board junction; no zebra crossing within 200 m"),
        ("anpr", "Route 101 · Connaught Place → Laxmi Nagar", "Delhi",
         "Bus-lane violation repeat offender; plate matched in 3 earlier alerts"),
    ]
    for i, (kind, route, city, notes) in enumerate(alert_specs):
        plate, conf, vtype = PLATES[i % len(PLATES)]
        pts = None
        for k, r in ROUTES.items():
            if k == city:
                pts = geo.get(r[0])
                break
        if not pts:
            continue
        lat, lon = pts[random.randrange(len(pts))]
        db.add(TrafficAlert(
            kind=kind, plate=plate if kind in ("anpr", "rash_driving") else None,
            plate_confidence=conf if kind in ("anpr", "rash_driving") else 0.0,
            vehicle_type=vtype if kind in ("anpr", "rash_driving") else "",
            lat=lat, lon=lon, city=city, notes=notes,
            detected_at=datetime.now(timezone.utc) - timedelta(minutes=8 + i * 14),
        ))
        n_alert += 1
    print(f"alerts: {n_alert}")

    db.commit()
    db.close()
    print("done")


if __name__ == "__main__":
    main()
