"""ORM models: vehicles, incidents (deduplicated), observations (raw detections), workflow updates."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return uuid.uuid4().hex


class IncidentStatus(str, enum.Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # e.g. "MH01BV4521" (plate)
    vehicle_type: Mapped[str] = mapped_column(String(24), default="bus")  # bus|garbage_truck|ambulance|tanker|municipal_car|...
    route: Mapped[str] = mapped_column(String(64), default="")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Observation(Base):
    """A raw detection pushed from an edge device (pre-dedup)."""
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    vehicle_code: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(48), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    bbox_area_px: Mapped[int] = mapped_column(Integer, default=0)
    speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    image_b64: Mapped[str | None] = mapped_column(Text, nullable=True)  # small blurred crop
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    deduped: Mapped[bool] = mapped_column(Boolean, default=False)

    incident: Mapped["Incident | None"] = relationship(back_populates="observations")


class Incident(Base):
    """A deduplicated, geo-tagged urban issue tracked through the workflow."""
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    label: Mapped[str] = mapped_column(String(48), index=True)
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    severity: Mapped[int] = mapped_column(Integer, default=1)          # 1 (low) .. 10 (critical)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus), default=IncidentStatus.NEW, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    observation_count: Mapped[int] = mapped_column(Integer, default=1)
    road_priority: Mapped[int] = mapped_column(Integer, default=5)
    assigned_dept: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    observations: Mapped[list[Observation]] = relationship(back_populates="incident")
    updates: Mapped[list["IncidentUpdate"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class IncidentUpdate(Base):
    """Workflow audit trail: every status change with an author + note."""
    __tablename__ = "incident_updates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    author: Mapped[str] = mapped_column(String(64), default="system")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="updates")


class TrafficSegment(Base):
    """Per-window traffic observation from a fleet vehicle: vehicle counts by
    class (COCO detector on the bus camera), pedestrian presence, speed and a
    0-100 congestion index."""
    __tablename__ = "traffic_segments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    city: Mapped[str] = mapped_column(String(32), index=True)
    route: Mapped[str] = mapped_column(String(64), index=True)
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    vehicle_counts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON {car: n, ...}
    total_vehicles: Mapped[int] = mapped_column(Integer, default=0)
    persons: Mapped[int] = mapped_column(Integer, default=0)
    speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    congestion: Mapped[int] = mapped_column(Integer, default=0, index=True)
    hour: Mapped[int] = mapped_column(Integer, default=12, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrafficAlert(Base):
    """Safety alert from the fleet: ANPR plate extraction (hit-and-run / rash
    driving evidence), vulnerable pedestrian situations (school zones)."""
    __tablename__ = "traffic_alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # anpr|rash_driving|pedestrian|school_zone
    plate: Mapped[str | None] = mapped_column(String(24), nullable=True)
    plate_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    vehicle_type: Mapped[str] = mapped_column(String(32), default="")
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    city: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
