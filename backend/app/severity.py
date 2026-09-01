"""Severity scoring: label base risk x confidence x road priority -> 1..10."""
from .config import settings

# Base risk per label (how dangerous / disruptive the issue is)
LABEL_BASE = {
    "pothole": 7,
    "crack": 4,
    "waterlogging": 6,
    "garbage_dump": 4,
    "illegal_parking": 3,
    "broken_streetlight": 5,
    "open_manhole": 9,
    "roadside_debris": 5,
    "faded_signage": 3,
}


def score(label: str, confidence: float, road_priority: int | None = None,
          observation_count: int = 1) -> int:
    base = LABEL_BASE.get(label, 4)
    priority = road_priority or settings.ROAD_PRIORITY_DEFAULT
    # confidence factor 0.7..1.1
    conf_f = 0.7 + 0.4 * min(max(confidence, 0.0), 1.0)
    # corroboration factor: multiple sightings push severity up (capped)
    count_f = min(1.0 + 0.1 * (observation_count - 1), 1.5)
    raw = base * conf_f * count_f * (priority / 5.0)
    return int(max(1, min(10, round(raw))))
