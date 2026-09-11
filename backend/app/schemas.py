"""Pydantic request/response contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from .models import IncidentStatus

# Canonical label taxonomy shared by edge + backend
LABELS = [
    "pothole",
    "crack",
    "waterlogging",
    "garbage_dump",
    "illegal_parking",
    "broken_streetlight",
    "open_manhole",
    "roadside_debris",
    "faded_signage",
]

# Which municipal department owns which label
DEPT_MAP = {
    "pothole": "Roads & Infrastructure",
    "crack": "Roads & Infrastructure",
    "waterlogging": "Drainage & Storm Water",
    "garbage_dump": "Solid Waste Management",
    "illegal_parking": "Traffic Police",
    "broken_streetlight": "Electricity / Street Lighting",
    "open_manhole": "Drainage & Storm Water",
    "roadside_debris": "Solid Waste Management",
    "faded_signage": "Traffic Police",
}


class ObservationIn(BaseModel):
    vehicle_code: str
    label: str
    confidence: float = Field(ge=0, le=1)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    detected_at: datetime | None = None
    bbox_area_px: int = 0
    speed_kmh: float = 0.0
    image_b64: str | None = None
    vehicle_type: str = "bus"   # bus|garbage_truck|ambulance|tanker|municipal_car|...


VEHICLE_TYPES = {"bus", "garbage_truck", "ambulance", "tanker",
                 "municipal_car", "police_car", "other"}


class IngestIn(BaseModel):
    observations: list[ObservationIn]


class IngestResult(BaseModel):
    received: int
    new_incidents: int
    merged: int


class IncidentUpdateIn(BaseModel):
    status: IncidentStatus
    author: str = "admin"
    note: str = ""
    assigned_dept: str | None = None


class VehicleOut(BaseModel):
    code: str
    vehicle_type: str
    route: str
    last_seen: datetime

    class Config:
        from_attributes = True


class FleetOut(BaseModel):
    fleet: list[VehicleOut]


class IncidentBase(BaseModel):
    id: str
    label: str
    lat: float
    lon: float
    address: str | None = None   # reverse-geocoded via Nominatim (OSM)
    severity: int
    status: IncidentStatus
    confidence: float
    observation_count: int
    assigned_dept: str | None
    has_image: bool = False       # evidence exists -> fetch via /image endpoint
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("created_at", "updated_at")
    def _utc(self, dt: datetime) -> str:
        # SQLite returns naive UTC datetimes; browsers parse those as LOCAL
        # time. Always mark them as UTC so client timestamps stay correct.
        return dt.isoformat() + ("" if dt.tzinfo else "Z")


class IncidentOut(IncidentBase):
    # full detail — includes the base64 evidence payload (single incident)
    image_b64: str | None = None


class IncidentListOut(IncidentBase):
    """List view — deliberately NO image_b64 field: the dashboard polls this
    every few seconds, and shipping ~15 KB of base64 per row multiplied
    into GBs of shared-pooler egress. Images are fetched on demand from
    GET /api/v1/incidents/{id}/image instead."""


class IncidentUpdateOut(BaseModel):
    id: str
    incident_id: str
    from_status: str
    to_status: str
    author: str
    note: str
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("created_at")
    def _utc(self, dt: datetime) -> str:
        return dt.isoformat() + ("" if dt.tzinfo else "Z")


class StatsOut(BaseModel):
    total: int
    open: int
    resolved: int
    avg_severity: float
    by_label: dict[str, int]
