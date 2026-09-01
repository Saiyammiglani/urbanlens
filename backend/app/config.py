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

    # Dedup engine tuning
    DEDUP_RADIUS_M: float = 35.0       # spatial dedup radius
    DEDUP_WINDOW_MIN: int = 240        # temporal window (minutes)

    # Road priority weights used by severity scoring (1-10)
    ROAD_PRIORITY_DEFAULT: int = 5


settings = Settings()
