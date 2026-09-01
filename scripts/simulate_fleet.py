"""Fleet simulator: N virtual buses driving replay routes, pushing observations
straight to the backend's HTTPS ingest — no camera/edge hardware needed.

This is the fastest way to demo the full pipeline:
    python simulate_fleet.py --buses 4 --minutes 2
"""
import argparse
import json
import math
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

LABELS = [
    "pothole", "crack", "waterlogging", "garbage_dump", "illegal_parking",
    "broken_streetlight", "open_manhole", "roadside_debris", "faded_signage",
]

ROUTES_DIR = Path(__file__).resolve().parents[1] / "edge" / "routes"


class VirtualBus:
    def __init__(self, code: str, route: list[dict], speed_kmh: float, seed: int):
        self.code = code
        self.waypoints = route
        self.speed = speed_kmh
        self.rng = random.Random(seed)
        self.seg = 0
        self.progress = 0.0
        # each bus patrols a jittered slice of the route so hot-spots repeat
        self.hotspots: list[tuple[float, float, str]] = []
        for _ in range(self.rng.randint(2, 4)):
            wp = self.rng.choice(route)
            self.hotspots.append((wp["lat"] + self.rng.uniform(-0.001, 0.001),
                                  wp["lon"] + self.rng.uniform(-0.001, 0.001),
                                  self.rng.choice(LABELS)))

    def step(self, dt: float) -> tuple[float, float]:
        a, b = self.waypoints[self.seg], self.waypoints[(self.seg + 1) % len(self.waypoints)]
        seg_m = math.hypot((b["lat"] - a["lat"]) * 111_000,
                           (b["lon"] - a["lon"]) * 111_000 * math.cos(math.radians(a["lat"])))
        self.progress += (self.speed / 3.6) * dt / max(seg_m, 1.0)
        if self.progress >= 1.0:
            self.progress = 0.0
            self.seg = (self.seg + 1) % (len(self.waypoints) - 1)
            a, b = self.waypoints[self.seg], self.waypoints[(self.seg + 1) % len(self.waypoints)]
        return (a["lat"] + (b["lat"] - a["lat"]) * self.progress,
                a["lon"] + (b["lon"] - a["lon"]) * self.progress)

    def maybe_detect(self, lat: float, lon: float) -> dict | None:
        # pass near a hotspot -> high chance of (re)detecting it => exercises dedup
        for hlat, hlon, label in self.hotspots:
            if math.hypot(lat - hlat, lon - hlon) < 0.0008 and self.rng.random() < 0.6:
                return {
                    "vehicle_code": self.code,
                    "label": label,
                    "confidence": round(self.rng.uniform(0.55, 0.96), 3),
                    "lat": round(hlat + self.rng.uniform(-1e-5, 1e-5), 6),
                    "lon": round(hlon + self.rng.uniform(-1e-5, 1e-5), 6),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "bbox_area_px": self.rng.randint(800, 20000),
                    "speed_kmh": round(self.speed + self.rng.uniform(-5, 5), 1),
                }
        # occasional random one-off detection
        if self.rng.random() < 0.04:
            return {
                "vehicle_code": self.code,
                "label": self.rng.choice(LABELS),
                "confidence": round(self.rng.uniform(0.4, 0.8), 3),
                "lat": round(lat + self.rng.uniform(-0.0005, 0.0005), 6),
                "lon": round(lon + self.rng.uniform(-0.0005, 0.0005), 6),
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "bbox_area_px": self.rng.randint(500, 9000),
                "speed_kmh": round(self.speed, 1),
            }
        return None


def run_bus(bus: VirtualBus, base_url: str, token: str, stop_at: float, tick: float = 1.0):
    url = f"{base_url.rstrip('/')}/api/v1/ingest"
    headers = {"X-API-Token": token}
    sent = 0
    while time.time() < stop_at:
        lat, lon = bus.step(tick)
        obs = bus.maybe_detect(lat, lon)
        if obs:
            try:
                r = requests.post(url, json={"observations": [obs]}, headers=headers, timeout=5)
                sent += 1
                log_line = f"[{bus.code}] {obs['label']}@({obs['lat']:.5f},{obs['lon']:.5f}) -> {r.status_code}"
                if r.status_code == 200:
                    body = r.json()
                    log_line += f" new={body['new_incidents']} merged={body['merged']}"
                print(log_line)
            except requests.RequestException as exc:
                print(f"[{bus.code}] network error: {exc}")
        time.sleep(tick)
    print(f"[{bus.code}] finished, {sent} observations sent")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--buses", type=int, default=3)
    p.add_argument("--backend", default="http://localhost:8000")
    p.add_argument("--token", default="sih-demo-token")
    p.add_argument("--minutes", type=float, default=2.0, help="simulation duration")
    args = p.parse_args()

    routes = [json.loads(r.read_text()) for r in sorted(ROUTES_DIR.glob("route_*.json"))]
    stop_at = time.time() + args.minutes * 60

    threads = []
    for i in range(args.buses):
        bus = VirtualBus(f"BL-BUS-{i + 1:03d}", routes[i % len(routes)],
                         speed_kmh=random.uniform(22, 34), seed=1000 + i)
        t = threading.Thread(target=run_bus, args=(bus, args.backend, args.token, stop_at), daemon=True)
        t.start()
        threads.append(t)
        print(f"launched {bus.code} with hotspots: {[(h[2]) for h in bus.hotspots]}")
        time.sleep(0.3)

    for t in threads:
        t.join()
    print("fleet simulation complete")


if __name__ == "__main__":
    main()
