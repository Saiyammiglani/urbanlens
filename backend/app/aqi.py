"""Air quality integration — two sources, both official:

Primary: data.gov.in "Real time Air Quality Index from various locations"
         (Central Pollution Control Board, Ministry of Environment) — per-station
         pollutant readings for Indian cities, keyed via DATAGOV_API_KEY.
Fallback: OpenAQ v3 (aggregates the same CPCB/DPCC feeds) via OPENAQ_API_KEY.

Exposes:
  GET /api/v1/aqi?lat&lon       -> nearest CPCB stations with live AQI
  GET /api/v1/aqi/correlation   -> garbage dumps vs air quality (impact view)
"""
import math
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter
from pydantic import BaseModel

from .config import settings

router = APIRouter(prefix="/api/v1/aqi", tags=["aqi"])

DATAGOV_RESOURCE = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
CACHE_TTL = 600          # 10 min (CPCB updates hourly)
_cache: dict[str, tuple] = {}


def _http_json(url: str, headers: dict | None = None) -> dict:
    req = Request(url, headers=headers or {"User-Agent": "UrbanLens/1.0"})
    with urlopen(req, timeout=12) as r:
        import json
        return json.loads(r.read().decode())


def _cached(key: str, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    data = fn()
    _cache[key] = (time.time(), data)
    return data


def _haversine_km(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111.0,
                      (lon2 - lon1) * 111.0 * math.cos(math.radians(lat1)))


def _f(s):
    """data.gov.in returns 'NA' strings — parse to float safely."""
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# CPCB National AQI breakpoints: concentration (ug/m3, 24h) -> sub-index
AQI_BREAKS = {
    "PM2.5": [(30, 50), (60, 100), (90, 200), (120, 300), (250, 400), (500, 500)],
    "PM10": [(50, 50), (100, 100), (250, 200), (350, 300), (430, 400), (520, 500)],
    "NO2": [(40, 50), (80, 100), (180, 200), (280, 300), (400, 400), (520, 500)],
    "SO2": [(40, 50), (80, 100), (380, 200), (800, 300), (1600, 400), (2400, 500)],
    "CO": [(1.0, 50), (2.0, 100), (10.0, 200), (17.0, 300), (34.0, 400), (50.0, 500)],  # mg/m3
    "OZONE": [(50, 50), (100, 100), (168, 200), (208, 300), (748, 400), (1000, 500)],
}
AQI_CATEGORIES = [(50, "Good"), (100, "Satisfactory"), (200, "Moderate"),
                  (300, "Poor"), (400, "Very Poor"), (500, "Severe")]


def _sub_index(conc: float | None, pollutant: str) -> int | None:
    """CPCB sub-index: piecewise-linear between breakpoints."""
    if conc is None:
        return None
    if pollutant == "CO":
        conc = conc / 1000.0  # data.gov.in reports CO in ug/m3; CPCB breakpoints are mg/m3
    breaks = AQI_BREAKS.get(pollutant)
    if not breaks:
        return None
    prev_c, prev_i = 0.0, 0
    for hi_c, hi_i in breaks:
        if conc <= hi_c:
            return round(prev_i + (conc - prev_c) / (hi_c - prev_c) * (hi_i - prev_i))
        prev_c, prev_i = hi_c, hi_i
    return 500


def _category(aqi: int | None) -> str:
    if aqi is None:
        return "unknown"
    for hi, cat in AQI_CATEGORIES:
        if aqi <= hi:
            return cat
    return "Severe"


def _nearest_city(lat: float, lon: float) -> str | None:
    """Rough lat/lon -> Indian metro match (data.gov.in filter is city-based)."""
    metros = [
        ("Delhi", 28.61, 77.21), ("Mumbai", 19.08, 72.88), ("Bengaluru", 12.97, 77.59),
        ("Kolkata", 22.57, 88.36), ("Chennai", 13.08, 80.27), ("Hyderabad", 17.39, 78.49),
        ("Pune", 18.52, 73.86), ("Ahmedabad", 23.02, 72.57), ("Jaipur", 26.91, 75.79),
        ("Lucknow", 26.85, 80.95),
    ]
    best, best_d = None, 1e9
    for name, mlat, mlon in metros:
        d = _haversine_km(lat, lon, mlat, mlon)
        if d < best_d:
            best, best_d = name, d
    return best if best and best_d < 120 else None


def _datagov_city(city: str) -> list[dict]:
    """All CPCB station readings for a city (primary source)."""
    if not settings.DATAGOV_API_KEY:
        return []
    url = (f"https://api.data.gov.in/resource/{DATAGOV_RESOURCE}"
           f"?api-key={settings.DATAGOV_API_KEY}&format=json&limit=1000"
           f"&filters%5Bcity%5D={quote(city)}")
    d = _cached(f"dg:{city}", lambda: _http_json(url))
    stations: dict[str, dict] = {}
    for r in d.get("records") or []:
        st = r.get("station", "")
        rec = stations.setdefault(st, {
            "name": st, "city": r.get("city"), "state": r.get("state"),
            "lat": _f(r.get("latitude")), "lon": _f(r.get("longitude")),
            "last_update": r.get("last_update"), "pollutants": {},
        })
        pid = r.get("pollutant_id")
        if pid:
            rec["pollutants"][pid] = {
                "avg": _f(r.get("avg_value")), "min": _f(r.get("min_value")),
                "max": _f(r.get("max_value")),
            }
    out = []
    for st in stations.values():
        pollutants = st["pollutants"]
        # AQI = worst sub-index across pollutants (CPCB method)
        sub_indices = {p: i for p, i in
                       ((p, _sub_index(v.get("avg"), p)) for p, v in pollutants.items())
                       if i is not None}
        aqi_val = max(sub_indices.values(), default=None)
        # dominant pollutant drives the index
        dominant = max(sub_indices, key=sub_indices.get) if sub_indices else None
        out.append({**st, "aqi": aqi_val, "category": _category(aqi_val),
                    "dominant_pollutant": dominant,
                    "pm25": pollutants.get("PM2.5", {}).get("avg"),
                    "pm10": pollutants.get("PM10", {}).get("avg")})
    return out


class StationOut(BaseModel):
    name: str
    city: str | None = None
    lat: float | None
    lon: float | None
    distance_km: float | None = None
    aqi: int | None = None
    category: str | None = None
    dominant_pollutant: str | None = None
    pm25: float | None = None
    pm10: float | None = None
    last_update: str | None = None
    source: str = "CPCB (data.gov.in)"


@router.get("")
def aqi(lat: float, lon: float, radius_km: float = 25.0) -> dict:
    """Live CPCB air quality for stations around a point."""
    city = _nearest_city(lat, lon)
    stations: list[dict] = []
    if city:
        stations = _datagov_city(city)
    if not stations:
        # fallback: OpenAQ (same CPCB/DPCC feeds, worldwide coverage)
        stations = _openaq_near(lat, lon)

    for st in stations:
        if st.get("lat") is not None:
            st["distance_km"] = round(_haversine_km(lat, lon, st["lat"], st["lon"]), 1)
        else:
            st["distance_km"] = None
    stations.sort(key=lambda s: s["distance_km"] if s["distance_km"] is not None else 9999)
    stations = stations[:15]
    with_aqi = [s for s in stations if s.get("aqi")]
    worst = max(with_aqi, key=lambda s: s["aqi"]) if with_aqi else None
    return {
        "center": {"lat": lat, "lon": lon, "city": city},
        "stations": stations,
        "worst": worst,
        "source": "CPCB via data.gov.in (Ministry of Environment)" if city else "OpenAQ",
    }


def _openaq_near(lat: float, lon: float, radius_km: float = 25.0) -> list[dict]:
    """OpenAQ v3 fallback when data.gov.in has no coverage for the area."""
    if not settings.OPENAQ_API_KEY:
        return []
    try:
        d = _cached(f"oaq:{round(lat,1)},{round(lon,1)}", lambda: _http_json(
            f"https://api.openaq.org/v3/locations?coordinates={lat},{lon}"
            f"&radius={int(radius_km * 1000)}&limit=10",
            headers={"X-API-Key": settings.OPENAQ_API_KEY}))
    except Exception:
        return []
    out = []
    for r in d.get("results", []):
        c = r.get("coordinates") or {}
        out.append({
            "name": r["name"], "city": None,
            "lat": c.get("latitude"), "lon": c.get("longitude"),
            "aqi": None, "pm25": None, "pm10": None,
            "last_update": None, "source": "OpenAQ (CPCB/DPCC feeds)",
        })
    return out


@router.get("/correlation")
def correlation(lat: float, lon: float) -> dict:
    """Open garbage-dump clusters vs station air quality — impact framing."""
    from .database import SessionLocal
    from .models import Incident
    db = SessionLocal()
    try:
        row = db.query(
            Incident.id
        ).filter(
            Incident.label == "garbage_dump",
            Incident.status.notin_(["resolved", "rejected"]),
        ).count()
        avg = db.query(Incident.severity).filter(
            Incident.label == "garbage_dump",
            Incident.status.notin_(["resolved", "rejected"]),
        )
        n = row
        avg_sev = sum(r[0] for r in avg) / n if n else 0.0
    finally:
        db.close()
    air = aqi(lat, lon)
    worst = air.get("worst") or {}
    aqi_v = worst.get("aqi")
    return {
        "open_garbage_dumps": n,
        "avg_dump_severity": round(avg_sev, 1),
        "city": air.get("center", {}).get("city"),
        "station": worst.get("name"),
        "station_distance_km": worst.get("distance_km"),
        "aqi": aqi_v,
        "category": worst.get("category"),
        "pm25": worst.get("pm25"),
        "action": (
            "prioritize collection in this ward — poor air quality with active dumps"
            if (aqi_v or 0) > 200 and n > 0 else
            "monitor: moderate correlation zone" if (aqi_v or 0) > 100 and n > 0 else
            "air quality acceptable near monitored dumps"
        ),
    }
