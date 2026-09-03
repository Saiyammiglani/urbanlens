"""Open-Meteo integration: current weather + rain forecast for incident context
and predictive waterlogging hotspots. Keyless — free open API.

- get_weather(lat, lon): current conditions (cached per ~10 min per ~10km grid)
- get_rain_risk(lat, lon): mm of rain in the next 6h + probability → risk score
- waterlogging_risk(incidents, weather): escalates open waterlogging/drainage
  incidents when heavy rain is forecast (predictive, not reactive)
"""
import math
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])

API = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL = 600  # 10 min
_cache: dict[tuple, tuple] = {}  # (grid lat, lon) -> (timestamp, data)


def _grid(lat: float, lon: float) -> tuple:
    return (round(lat, 1), round(lon, 1))  # ~11 km grid


def _fetch(lat: float, lon: float) -> dict:
    key = _grid(lat, lon)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]

    params = urlencode({
        "latitude": key[0], "longitude": key[1],
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code",
        "hourly": "precipitation,precipitation_probability",
        "forecast_days": 2, "timezone": "Asia/Kolkata",
    })
    with urlopen(f"{API}?{params}", timeout=10) as r:
        data = json_load(r)
    _cache[key] = (now, data)
    return data


def json_load(r) -> dict:
    import json
    return json.loads(r.read().decode())


def get_weather(lat: float, lon: float) -> dict:
    d = _fetch(lat, lon)
    c = d.get("current", {})
    return {
        "temperature_c": c.get("temperature_2m"),
        "humidity_pct": c.get("relative_humidity_2m"),
        "precipitation_mm": c.get("precipitation"),
        "weather_code": c.get("weather_code"),
        "time": c.get("time"),
    }


def get_rain_risk(lat: float, lon: float) -> dict:
    """Rain expected in the next 6 hours (from now, local time)."""
    d = _fetch(lat, lon)
    hourly = d.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return {"rain_mm_6h": 0.0, "rain_probability": 0, "risk": 0}
    now_key = d.get("current", {}).get("time", "")[:13]
    start = 0
    for i, t in enumerate(times):
        if t[:13] >= now_key:
            start = i
            break
    window = slice(start, start + 6)
    rain = [x or 0 for x in hourly.get("precipitation", [])[window]]
    prob = hourly.get("precipitation_probability", [])[window] or [0]
    rain_mm = sum(rain)
    max_prob = max(prob) if prob else 0
    # risk 0..10: 2.5mm/h sustained = heavy; 10mm total = severe
    risk = min(10, round(rain_mm / 1.2 + max_prob / 20.0, 1))
    return {"rain_mm_6h": round(rain_mm, 1), "rain_probability": max_prob, "risk": risk}


@router.get("")
def weather(lat: float, lon: float) -> dict:
    return {"location": {"lat": round(lat, 4), "lon": round(lon, 4)},
            **get_weather(lat, lon), "rain": get_rain_risk(lat, lon)}


@router.get("/waterlogging-risk")
def waterlogging_risk(lat: float, lon: float) -> dict:
    """Predictive overlay: how likely existing waterlogging spots get worse."""
    rain = get_rain_risk(lat, lon)
    advisory = (
        "severe" if rain["risk"] >= 7 else
        "high" if rain["risk"] >= 4.5 else
        "moderate" if rain["risk"] >= 2 else
        "low"
    )
    return {**rain, "advisory": advisory,
            "note": "escalate open waterlogging/drainage incidents in this area"}


# ---------- reverse geocoding (Nominatim, keyless) ----------

GEO_CACHE: dict[tuple, str] = {}


def reverse_geocode(lat: float, lon: float) -> str | None:
    """'28.61, 77.20' -> 'Connaught Place, New Delhi'. Cached forever (places don't move)."""
    key = (round(lat, 3), round(lon, 3))  # ~110 m — same spot = same address
    if key in GEO_CACHE:
        return GEO_CACHE[key]
    url = (f"https://nominatim.openstreetmap.org/reverse?format=jsonv2"
           f"&lat={key[0]}&lon={key[1]}&zoom=16&addressdetails=1")
    req_headers = {"User-Agent": "UrbanLens-SIH26124/1.0 (urban monitoring platform)"}
    from urllib.request import Request, urlopen
    req = Request(url, headers=req_headers)
    try:
        with urlopen(req, timeout=8) as r:
            data = json_load(r)
    except Exception:
        return None
    a = data.get("address", {})
    parts = [a.get("road"), a.get("neighbourhood") or a.get("suburb"),
             a.get("city_district") or a.get("city"), a.get("state", "")]
    addr = ", ".join(p for p in parts if p and p.strip())
    if addr:
        GEO_CACHE[key] = addr
    return addr or None
