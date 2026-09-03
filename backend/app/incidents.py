"""Workflow state machine for incidents.

Transitions:
  NEW -> CONFIRMED -> ASSIGNED -> IN_PROGRESS -> RESOLVED
  any open state -> REJECTED
  RESOLVED -> IN_PROGRESS (reopened)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Incident, IncidentStatus, IncidentUpdate, Vehicle
from .schemas import IncidentOut, IncidentUpdateIn, IncidentUpdateOut, StatsOut, FleetOut

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

# statuses that still need crew attention (REJECTED and RESOLVED are closed)
OPEN_STATUSES = (
    IncidentStatus.NEW,
    IncidentStatus.CONFIRMED,
    IncidentStatus.ASSIGNED,
    IncidentStatus.IN_PROGRESS,
)

ALLOWED = {
    IncidentStatus.NEW: {IncidentStatus.CONFIRMED, IncidentStatus.REJECTED},
    IncidentStatus.CONFIRMED: {IncidentStatus.ASSIGNED, IncidentStatus.REJECTED},
    IncidentStatus.ASSIGNED: {IncidentStatus.IN_PROGRESS, IncidentStatus.REJECTED},
    IncidentStatus.IN_PROGRESS: {IncidentStatus.RESOLVED, IncidentStatus.REJECTED},
    IncidentStatus.RESOLVED: {IncidentStatus.IN_PROGRESS},  # reopen
    IncidentStatus.REJECTED: {IncidentStatus.CONFIRMED},     # re-verify
}


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    status: IncidentStatus | None = Query(default=None),
    label: str | None = Query(default=None),
    min_severity: int = Query(default=1, ge=1, le=10),
    limit: int = Query(default=200, le=1000),
    with_address: bool = Query(default=False, description="reverse-geocode incidents (slower, cached)"),
    db: Session = Depends(get_db),
):
    q = select(Incident).where(Incident.severity >= min_severity).limit(limit)
    if status is not None:
        q = q.where(Incident.status == status)
    if label:
        q = q.where(Incident.label == label)
    rows = db.execute(q.order_by(Incident.severity.desc(), Incident.created_at.desc())).scalars().all()
    if with_address:
        from .weather import reverse_geocode
        # detail view only: cacheable, one request per ~110m spot
        for inc in rows[:50]:  # cap so list stays fast
            inc.address = reverse_geocode(inc.lat, inc.lon) or None
    return rows


@router.get("/fleet", response_model=FleetOut)
def fleet(db: Session = Depends(get_db)):
    """Active government fleet vehicles reporting to the platform."""
    vehicles = db.query(Vehicle).order_by(Vehicle.last_seen.desc()).limit(200).all()
    return {"fleet": vehicles}


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    total = db.execute(select(func.count(Incident.id))).scalar() or 0
    resolved = db.execute(
        select(func.count(Incident.id)).where(Incident.status == IncidentStatus.RESOLVED)
    ).scalar() or 0
    open_count = db.execute(
        select(func.count(Incident.id)).where(Incident.status.in_(OPEN_STATUSES))
    ).scalar() or 0
    avg_sev = db.execute(select(func.avg(Incident.severity))).scalar() or 0.0
    rows = db.execute(
        select(Incident.label, func.count(Incident.id)).group_by(Incident.label)
    ).all()
    return StatsOut(
        total=total,
        open=open_count,
        resolved=resolved,
        avg_severity=round(float(avg_sev), 2),
        by_label={label: count for label, count in rows},
    )


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(404, "incident not found")
    from .weather import reverse_geocode
    inc.address = reverse_geocode(inc.lat, inc.lon) or None
    return inc


@router.get("/{incident_id}/updates", response_model=list[IncidentUpdateOut])
def get_updates(incident_id: str, db: Session = Depends(get_db)):
    return db.execute(
        select(IncidentUpdate).where(IncidentUpdate.incident_id == incident_id)
        .order_by(IncidentUpdate.created_at.desc())
    ).scalars().all()


@router.post("/{incident_id}/transition", response_model=IncidentOut)
def transition(incident_id: str, payload: IncidentUpdateIn, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(404, "incident not found")
    target = payload.status
    if target not in ALLOWED.get(inc.status, set()):
        raise HTTPException(
            422,
            f"illegal transition {inc.status.value} -> {target.value}. "
            f"Allowed: {[s.value for s in ALLOWED.get(inc.status, set())]}",
        )
    from_status = inc.status
    inc.status = target
    if payload.assigned_dept:
        inc.assigned_dept = payload.assigned_dept
    if target == IncidentStatus.RESOLVED:
        from .models import utcnow
        inc.resolved_at = utcnow()
    db.add(IncidentUpdate(
        incident_id=inc.id,
        from_status=from_status.value,
        to_status=target.value,
        author=payload.author,
        note=payload.note,
    ))
    db.commit()
    db.refresh(inc)
    return inc
