"""Traffic intelligence: vehicle counts, congestion, bottlenecks, ANPR/pedestrian
alerts, OD flows, route delays — aggregated from the bus fleet.

Endpoints:
    GET /api/v1/traffic/segments     — congestion segments (heatmap + list)
    GET /api/v1/traffic/bottlenecks  — worst corridors ranked
    GET /api/v1/traffic/alerts       — ANPR / rash-driving / pedestrian alerts
    GET /api/v1/traffic/od           — origin-destination flow matrix
    GET /api/v1/traffic/delays       — per-route delay estimates by hour
"""
from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import TrafficAlert, TrafficSegment

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])


# --- live ingest from the fleet ---------------------------------------------

class TrafficSegmentIn(BaseModel):
    """One 10-second counting window pushed by a bus running the COCO
    detector (edge/traffic_counter.py). Real inference on the live feed."""
    vehicle_code: str
    route: str = "route_01"
    lat: float
    lon: float
    vehicle_counts: dict[str, int] = {}
    total_vehicles: int = 0
    persons: int = 0
    speed_kmh: float = 0.0
    congestion: int = 0


CITY_CENTERS = {   # nearest-city tagging for live segments (mirrors dashboard)
    "Delhi": (28.614, 77.209), "Mumbai": (19.018, 72.856),
    "Bengaluru": (12.972, 77.594),
}


def _nearest_city(lat: float, lon: float) -> str:
    return min(CITY_CENTERS, key=lambda c: (CITY_CENTERS[c][0] - lat) ** 2
               + (CITY_CENTERS[c][1] - lon) ** 2)


@router.post("/ingest")
def ingest_segment(payload: TrafficSegmentIn,
                   db: Session = Depends(get_db),
                   x_api_token: str = Header(default="")):
    from .config import settings
    if x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    seg = TrafficSegment(
        city=_nearest_city(payload.lat, payload.lon),
        route=payload.route,
        lat=payload.lat, lon=payload.lon,
        vehicle_counts=json.dumps(payload.vehicle_counts),
        total_vehicles=payload.total_vehicles,
        persons=payload.persons,
        speed_kmh=payload.speed_kmh,
        congestion=payload.congestion,
        hour=datetime.now(timezone.utc).hour,
    )
    db.add(seg)
    db.commit()
    return {"ok": True, "id": seg.id, "city": seg.city, "congestion": seg.congestion}


class AlertIn(BaseModel):
    """Live alert from the fleet — ANPR plate reads (edge/anpr.py) or
    rash-driving detections (edge/anpr.py tracking heuristics)."""
    kind: str                     # anpr | stolen | rash_driving
    plate: str | None = None
    plate_confidence: float | None = None
    vehicle_type: str | None = None
    lat: float | None = None
    lon: float | None = None
    notes: str | None = None


@router.post("/anpr")
def ingest_alert(payload: AlertIn,
                 db: Session = Depends(get_db),
                 x_api_token: str = Header(default="")):
    from .config import settings
    if x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    if payload.lat is not None and payload.lon is not None:
        city = _nearest_city(payload.lat, payload.lon)
    else:
        city = None
    a = TrafficAlert(
        kind=payload.kind, plate=payload.plate,
        plate_confidence=payload.plate_confidence,
        vehicle_type=payload.vehicle_type,
        lat=payload.lat, lon=payload.lon, city=city,
        notes=payload.notes,
    )
    db.add(a)
    db.commit()
    return {"ok": True, "id": a.id, "kind": a.kind, "city": a.city}


def _seg_out(s: TrafficSegment) -> dict:
    return {
        "id": s.id,
        "city": s.city,
        "route": s.route,
        "lat": s.lat,
        "lon": s.lon,
        "vehicle_counts": s.vehicle_counts or {},
        "total_vehicles": s.total_vehicles,
        "persons": s.persons,
        "speed_kmh": s.speed_kmh,
        "congestion": s.congestion,
        "hour": s.hour,
        "recorded_at": s.recorded_at.isoformat() if s.recorded_at else None,
    }


def _alert_out(a: TrafficAlert) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,          # anpr | rash_driving | pedestrian | school_zone
        "plate": a.plate,
        "plate_confidence": a.plate_confidence,
        "vehicle_type": a.vehicle_type,
        "lat": a.lat,
        "lon": a.lon,
        "city": a.city,
        "notes": a.notes,
        "detected_at": a.detected_at.isoformat() if a.detected_at else None,
    }


@router.get("/segments")
def segments(city: str | None = None, hour: int | None = None,
             min_congestion: int = 0, limit: int = 500,
             db: Session = Depends(get_db)):
    q = select(TrafficSegment).where(TrafficSegment.congestion >= min_congestion)
    if city:
        q = q.where(TrafficSegment.city == city)
    if hour is not None:
        q = q.where(TrafficSegment.hour == hour)
    q = q.order_by(desc(TrafficSegment.congestion)).limit(limit)
    return [_seg_out(s) for s in db.scalars(q)]


@router.get("/bottlenecks")
def bottlenecks(city: str | None = None, limit: int = 8,
                db: Session = Depends(get_db)):
    """Worst corridors: avg congestion grouped by route, ranked."""
    from sqlalchemy import func
    q = (
        select(
            TrafficSegment.route,
            func.avg(TrafficSegment.congestion).label("avg_congestion"),
            func.avg(TrafficSegment.speed_kmh).label("avg_speed"),
            func.sum(TrafficSegment.total_vehicles).label("vehicles"),
            func.count().label("n"),
        )
        .group_by(TrafficSegment.route)
    )
    if city:
        q = q.where(TrafficSegment.city == city)
    rows = db.execute(q).all()
    out = [
        {
            "route": r.route,
            "avg_congestion": round(float(r.avg_congestion or 0), 1),
            "avg_speed_kmh": round(float(r.avg_speed or 0), 1),
            "vehicles_total": int(r.vehicles or 0),
            "segments": int(r.n),
        }
        for r in rows
    ]
    out.sort(key=lambda x: -x["avg_congestion"])
    return out[:limit]


@router.get("/alerts")
def alerts(kind: str | None = None, city: str | None = None, limit: int = 50,
           db: Session = Depends(get_db)):
    q = select(TrafficAlert).order_by(desc(TrafficAlert.detected_at)).limit(limit)
    if kind:
        q = q.where(TrafficAlert.kind == kind)
    if city:
        q = q.where(TrafficAlert.city == city)
    return [_alert_out(a) for a in db.scalars(q)]


@router.get("/od")
def od_flows(city: str | None = None, db: Session = Depends(get_db)):
    """Origin-destination estimated flows (from fleet GPS + vehicle counts)."""
    from sqlalchemy import func
    q = select(TrafficSegment.route, func.sum(TrafficSegment.total_vehicles)).group_by(TrafficSegment.route)
    if city:
        q = q.where(TrafficSegment.city == city)
    per_route = {r[0]: int(r[1] or 0) for r in db.execute(q).all()}

    # zone centroids come from segment averages per route
    zones = {}
    q2 = select(
        TrafficSegment.route,
        func.avg(TrafficSegment.lat), func.avg(TrafficSegment.lon),
    ).group_by(TrafficSegment.route)
    if city:
        q2 = q2.where(TrafficSegment.city == city)
    for route, lat, lon in db.execute(q2).all():
        zones[route] = {"lat": float(lat), "lon": float(lon), "volume": per_route.get(route, 0)}

    # build pairwise OD flows (adjacent routes on the network)
    names = sorted(zones)
    flows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            va, vb = zones[a]["volume"], zones[b]["volume"]
            if va and vb:
                flows.append({
                    "from": a, "to": b,
                    "from_lat": zones[a]["lat"], "from_lon": zones[a]["lon"],
                    "to_lat": zones[b]["lat"], "to_lon": zones[b]["lon"],
                    "volume": int((va + vb) / 2),
                })
    flows.sort(key=lambda f: -f["volume"])
    return {"zones": [{"name": k, **v} for k, v in zones.items()], "flows": flows[:12]}


@router.get("/delays")
def delays(city: str | None = None, db: Session = Depends(get_db)):
    """Route delay estimates vs free-flow, by hour of day."""
    from sqlalchemy import func
    q = select(
        TrafficSegment.route,
        TrafficSegment.hour,
        func.avg(TrafficSegment.speed_kmh).label("avg_speed"),
        func.avg(TrafficSegment.congestion).label("avg_cong"),
    ).group_by(TrafficSegment.route, TrafficSegment.hour).order_by(TrafficSegment.route, TrafficSegment.hour)
    if city:
        q = q.where(TrafficSegment.city == city)
    out = {}
    FREE_FLOW = 40.0  # km/h typical urban free-flow for buses
    for route, hour, speed, cong in db.execute(q).all():
        speed = float(speed or 0)
        delay_pct = max(0.0, round((1 - speed / FREE_FLOW) * 100, 1)) if speed else 0.0
        out.setdefault(route, []).append({
            "hour": int(hour), "avg_speed_kmh": round(speed, 1),
            "delay_pct": delay_pct,
            "congestion": round(float(cong or 0), 1),
        })
    return {"routes": [
        {"route": r, "hours": h} for r, h in sorted(out.items())
    ]}
