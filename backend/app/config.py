"""Central configuration loaded from environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL") or f"sqlite:///{ROOT / 'urbanlens.sqlite3'}"
    MQTT_HOST: str = os.getenv("MQTT_HOST", "")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_TOPIC: str = os.getenv("MQTT_TOPIC", "urbanlens/ingest")
    RUN_MQTT_WORKER: bool = os.getenv("RUN_MQTT_WORKER", "0") == "1"
    API_TOKEN: str = os.getenv("API_TOKEN", "sih-demo-token")

    # External data APIs (free tiers) — keys live in .env, never committed
    OPENAQ_API_KEY: str = os.getenv("OPENAQ_API_KEY", "")
    DATAGOV_API_KEY: str = os.getenv("DATAGOV_API_KEY", "")

    # Edge agent launcher (used by the media upload page)
    EDGE_PYTHON: str = os.getenv("EDGE_PYTHON") or str(
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe"
    )

    # Dedup engine tuning
    DEDUP_RADIUS_M: float = 35.0       # spatial dedup radius
    DEDUP_WINDOW_MIN: int = 240        # temporal window (minutes)

    # Road priority weights used by severity scoring (1-10)
    ROAD_PRIORITY_DEFAULT: int = 5


settings = Settings()
