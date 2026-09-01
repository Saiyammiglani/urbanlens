"""MQTT consumer: bridges Mosquitto messages into the ingestion pipeline.

Each MQTT message payload is a single JSON observation (edge sends one message
per incident to keep payloads tiny and loss-tolerant).
"""
import json
import logging
import threading

from .config import settings
from .database import SessionLocal
from .ingest import process_observation
from .schemas import ObservationIn

log = logging.getLogger("urbanlens.mqtt")


def handle_message(payload: bytes) -> None:
    try:
        data = json.loads(payload)
        obs = ObservationIn(**data)
    except Exception:
        log.warning("dropping malformed MQTT payload: %r", payload[:200])
        return
    db = SessionLocal()
    try:
        process_observation(db, obs)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("failed to process observation")
    finally:
        db.close()


def run_worker(background: bool = False) -> None:
    import paho.mqtt.client as mqtt

    def on_connect(client, *_args):
        client.subscribe(settings.MQTT_TOPIC)
        log.info("subscribed to %s", settings.MQTT_TOPIC)

    def on_message(_client, _userdata, msg):
        handle_message(msg.payload)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="urbanlens-backend")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)

    if background:
        threading.Thread(target=client.loop_forever, daemon=True, name="mqtt-worker").start()
    else:
        log.info("MQTT worker running in foreground — Ctrl+C to stop")
        client.loop_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
