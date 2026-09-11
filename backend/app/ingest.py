"""Ingestion endpoint: observations -> dedup -> severity -> persist."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from .auth import require_token
from sqlalchemy.orm import Session

from . import severity
from .database import get_db
from .dedup import find_matching_incident
from .models import Incident, Observation, Vehicle
from .schemas import DEPT_MAP, LABELS, VEHICLE_TYPES, IngestIn, IngestResult, ObservationIn

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def process_observation(db: Session, obs: ObservationIn) -> bool:
    """Persist one observation. Returns True if a NEW incident was created."""
    if obs.label not in LABELS:
        return False  # silently drop unknown labels (edge contract)

    detected_at = obs.detected_at or datetime.now(timezone.utc)

    # keep vehicle registry fresh
    vtype = (obs.vehicle_type or "bus").strip().lower()
    if vtype not in VEHICLE_TYPES:
        vtype = "other"
    vehicle = db.query(Vehicle).filter(Vehicle.code == obs.vehicle_code).one_or_none()
    if vehicle is None:
        vehicle = Vehicle(code=obs.vehicle_code, vehicle_type=vtype)
        db.add(vehicle)
        db.flush()  # visible to later lookups in the same batch (avoids dup INSERT) 
    elif vehicle.vehicle_type != vtype:
        vehicle.vehicle_type = vtype  # adopt latest reported type
    vehicle.last_seen = datetime.now(timezone.utc)

    existing = find_matching_incident(db, obs.label, obs.lat, obs.lon, detected_at)

    record = Observation(
        vehicle_code=obs.vehicle_code,
        label=obs.label,
        confidence=obs.confidence,
        lat=obs.lat,
        lon=obs.lon,
        detected_at=detected_at,
        bbox_area_px=obs.bbox_area_px,
        speed_kmh=obs.speed_kmh,
        image_b64=obs.image_b64,
    )

    if existing is not None:
        # merge into existing incident: bump count, refresh severity & recency
        record.incident_id = existing.id
        record.deduped = True
        existing.observation_count += 1
        existing.confidence = max(existing.confidence, obs.confidence)
        existing.severity = severity.score(
            existing.label, existing.confidence,
            existing.road_priority, existing.observation_count,
        )
        if not existing.image_b64 and obs.image_b64:
            existing.image_b64 = obs.image_b64
        db.add(record)
        return False

    # brand-new incident
    incident = Incident(
        label=obs.label,
        lat=obs.lat,
        lon=obs.lon,
        confidence=obs.confidence,
        severity=severity.score(obs.label, obs.confidence),
        assigned_dept=DEPT_MAP.get(obs.label),
        image_b64=obs.image_b64,
    )
    db.add(incident)
    db.flush()
    record.incident_id = incident.id
    db.add(record)
    return True


@router.post("", response_model=IngestResult, dependencies=[Depends(require_token)])
def ingest(
    payload: IngestIn,
    db: Session = Depends(get_db),
) -> IngestResult:
    new_incidents = 0
    for obs in payload.observations:
        if process_observation(db, obs):
            new_incidents += 1
    db.commit()

    received = len(payload.observations)
    return IngestResult(received=received, new_incidents=new_incidents,
                        merged=received - new_incidents)
