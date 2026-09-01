"""Uploader: pushes observations to the cloud via MQTT (preferred) or HTTPS.

Both transports are best-effort; failures land back in the spool.
"""
import json
import logging

import requests

log = logging.getLogger("urbanlens.edge.uploader")


class HTTPSUploader:
    def __init__(self, base_url: str, api_token: str, batch_size: int = 50):
        self.url = f"{base_url.rstrip('/')}/api/v1/ingest"
        self.headers = {"X-API-Token": api_token}
        self.batch_size = batch_size

    def send(self, records: list[dict]) -> bool:
        """POST observations. Returns True only if server accepted them."""
        if not records:
            return True
        try:
            resp = requests.post(
                self.url,
                json={"observations": records[: self.batch_size]},
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                remaining = records[self.batch_size:]
                return self.send(remaining) if remaining else True
            log.warning("server rejected batch: %s %s", resp.status_code, resp.text[:200])
        except requests.RequestException as exc:
            log.warning("network error: %s", exc)
        return False


class MQTTUploader:
    def __init__(self, host: str, port: int, topic: str):
        import paho.mqtt.client as mqtt
        self.topic = topic
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"edge-{id(self)}")
        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()

    def send(self, records: list[dict]) -> bool:
        """MQTT QoS1 gives at-least-once delivery; treat as fire-and-forget."""
        for rec in records:
            self.client.publish(self.topic, json.dumps(rec), qos=1)
        return True

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def make_uploader(backend_url: str | None, mqtt_host: str | None,
                  mqtt_port: int, mqtt_topic: str, api_token: str):
    if mqtt_host:
        log.info("using MQTT transport: %s:%d/%s", mqtt_host, mqtt_port, mqtt_topic)
        return MQTTUploader(mqtt_host, mqtt_port, mqtt_topic)
    if backend_url:
        log.info("using HTTPS transport: %s", backend_url)
        return HTTPSUploader(backend_url, api_token)
    raise ValueError("no transport configured: set MQTT_HOST or EDGE_BACKEND_URL")


def record_from_detection(det, fix, vehicle_code: str, image_b64: str | None) -> dict:
    """Shape must match backend ObservationIn exactly."""
    from datetime import datetime, timezone
    return {
        "vehicle_code": vehicle_code,
        "label": det.label,
        "confidence": round(det.confidence, 4),
        "lat": round(fix.lat, 6),
        "lon": round(fix.lon, 6),
        "detected_at": datetime.fromtimestamp(fix.timestamp, tz=timezone.utc).isoformat(),
        "bbox_area_px": int((det.bbox[2] - det.bbox[0]) * (det.bbox[3] - det.bbox[1])),
        "speed_kmh": round(fix.speed_kmh, 1),
        "image_b64": image_b64,
    }
