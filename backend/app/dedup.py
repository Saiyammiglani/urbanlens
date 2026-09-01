"""Spatial dedup: merges new observations into nearby open incidents.

Uses a haversine radius + time window + same-label match. Designed so H3
hex-indexing can drop in later by replacing `nearby()` only.
"""
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Incident, IncidentStatus, Observation

OPEN_STATUSES = (
    IncidentStatus.NEW,
    IncidentStatus.CONFIRMED,
    IncidentStatus.ASSIGNED,
    IncidentStatus.IN_PROGRESS,
)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * 6371000 * asin(sqrt(a))


def _naive(dt: datetime) -> datetime:
    """SQLite returns offset-naive datetimes; normalize for comparison."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def find_matching_incident(
    db: Session, label: str, lat: float, lon: float, detected_at: datetime
) -> Incident | None:
    """Return the nearest open incident of the same label within radius+window."""
    detected_at = _naive(detected_at)
    window_start = detected_at - timedelta(minutes=settings.DEDUP_WINDOW_MIN)
    # cheap bbox pre-filter (~0.01 deg) before exact haversine
    d = 0.01
    candidates = db.execute(
        select(Incident).where(
            Incident.label == label,
            Incident.status.in_(OPEN_STATUSES),
            Incident.lat.between(lat - d, lat + d),
            Incident.lon.between(lon - d, lon + d),
        )
    ).scalars().all()

    best, best_dist = None, settings.DEDUP_RADIUS_M
    for inc in candidates:
        if _naive(inc.created_at) < window_start:
            continue
        dist = haversine_m(lat, lon, inc.lat, inc.lon)
        if dist <= best_dist:
            best, best_dist = inc, dist
    return best
