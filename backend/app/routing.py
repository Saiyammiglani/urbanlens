"""Route advisory: cluster open incidents into hazard zones for citizen routing.

A "hazard zone" is a cluster of open incidents within CLUSTER_M metres of each
other. Zones let navigation apps steer commuters around concentrations of
potholes / waterlogging / debris instead of around individual points.
"""
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Incident, IncidentStatus

router = APIRouter(prefix="/api/v1/routing", tags=["routing"])

CLUSTER_M = 250.0          # incidents within this distance merge into one zone
EARTH_R = 6_371_000.0


def _haversine(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(a))


@router.get("/zones")
def hazard_zones(
    min_severity: int = Query(default=4, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Return hazard zones (clusters of open incidents) for route planning."""
    incs = db.execute(
        select(Incident)
        .where(Incident.severity >= min_severity)
        .where(Incident.status.in_(
            [IncidentStatus.NEW, IncidentStatus.CONFIRMED,
             IncidentStatus.ASSIGNED, IncidentStatus.IN_PROGRESS]
        ))
    ).scalars().all()

    # greedy clustering: seed a zone from the first unused incident, absorb
    # everything within CLUSTER_M of the zone centroid, iterate.
    points = [{"lat": i.lat, "lon": i.lon, "severity": i.severity,
               "label": i.label} for i in incs]
    zones = []
    unused = list(range(len(points)))
    while unused:
        seed = points[unused.pop(0)]
        members = [seed]
        changed = True
        while changed:
            changed = False
            lat = sum(m["lat"] for m in members) / len(members)
            lon = sum(m["lon"] for m in members) / len(members)
            for idx in list(unused):
                p = points[idx]
                if _haversine(lat, lon, p["lat"], p["lon"]) <= CLUSTER_M:
                    members.append(p)
                    unused.remove(idx)
                    changed = True
        lat = sum(m["lat"] for m in members) / len(members)
        lon = sum(m["lon"] for m in members) / len(members)
        radius = max(
            (_haversine(lat, lon, m["lat"], m["lon"]) for m in members),
            default=0,
        )
        labels = {}
        for m in members:
            labels[m["label"]] = labels.get(m["label"], 0) + 1
        zones.append({
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "radius_m": round(max(radius, 60), 1),   # visual minimum
            "incident_count": len(members),
            "max_severity": max(m["severity"] for m in members),
            "avg_severity": round(sum(m["severity"] for m in members) / len(members), 1),
            "labels": labels,
            "advisory": _advisory(labels, max(m["severity"] for m in members)),
        })

    zones.sort(key=lambda z: (-z["max_severity"], -z["incident_count"]))
    return {"zone_count": len(zones), "zones": zones}


def _advisory(labels: dict, max_sev: int) -> str:
    top = max(labels, key=labels.get).replace("_", " ")
    if max_sev >= 8:
        return f"Avoid: severe {top} reported here"
    if max_sev >= 6:
        return f"Caution: multiple {top} issues here"
    return f"Minor {top} issues here"
