"""GPS: real serial NMEA reader, or deterministic route replay for demos."""
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fix:
    lat: float
    lon: float
    speed_kmh: float
    heading: float
    timestamp: float


def _nmea_to_deg(value: str, hemi: str) -> float:
    deg = float(value[:2]) if hemi in "NS" else float(value[:3])
    minutes = float(value[2:] if hemi in "NS" else value[3:])
    d = deg + minutes / 60.0
    return -d if hemi in "SW" else d


class SerialGPS:
    """Reads NMEA sentences from a hardware GPS puck (e.g. NEO-6M)."""

    def __init__(self, port: str, baud: int = 9600):
        import serial  # pyserial
        self.ser = serial.Serial(port, baud, timeout=1)

    def read(self) -> Fix | None:
        line = self.ser.readline().decode("ascii", errors="ignore").strip()
        if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
            parts = line.split(",")
            if parts[2] != "A":  # invalid fix
                return None
            return Fix(
                lat=_nmea_to_deg(parts[3], parts[4]),
                lon=_nmea_to_deg(parts[5], parts[6]),
                speed_kmh=float(parts[7]) * 1.852,
                heading=float(parts[8]) if parts[8] else 0.0,
                timestamp=time.time(),
            )
        return None


class ReplayGPS:
    """Interpolates along a waypoint route; deterministic and demo-friendly.

    Route files are JSON: [{"lat":..,"lon":..}, ...] stored in edge/routes/.
    ``origin`` translates the whole route so its first waypoint starts at the
    given real device coordinates (e.g. from the uploading phone/laptop).
    """

    def __init__(self, route_file: str | Path, speed_kmh: float = 28.0, loop: bool = True,
                 origin: tuple[float, float] | None = None):
        self.waypoints = json.loads(Path(route_file).read_text())
        if len(self.waypoints) < 2:
            raise ValueError("route needs >= 2 waypoints")
        if origin is not None:
            dlat = origin[0] - self.waypoints[0]["lat"]
            dlon = origin[1] - self.waypoints[0]["lon"]
            for wp in self.waypoints:
                wp["lat"] += dlat
                wp["lon"] += dlon
        self.speed_kmh = speed_kmh
        self.loop = loop
        self._seg = 0
        self._progress = 0.0
        self._last_time = time.time()

    def _interp(self, a: dict, b: dict, t: float) -> Fix:
        return Fix(
            lat=a["lat"] + (b["lat"] - a["lat"]) * t,
            lon=a["lon"] + (b["lon"] - a["lon"]) * t,
            speed_kmh=self.speed_kmh,
            heading=math.degrees(math.atan2(b["lon"] - a["lon"], b["lat"] - a["lat"])) % 360,
            timestamp=time.time(),
        )

    def read(self) -> Fix | None:
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        a, b = self.waypoints[self._seg], self.waypoints[self._seg + 1]
        seg_len_m = math.hypot(
            (b["lat"] - a["lat"]) * 111_000,
            (b["lon"] - a["lon"]) * 111_000 * math.cos(math.radians(a["lat"])),
        )
        if seg_len_m < 1:
            step = 1.0
        else:
            step = (self.speed_kmh / 3.6) * dt / seg_len_m

        self._progress += step
        while self._progress >= 1.0:
            self._progress -= 1.0
            self._seg += 1
            if self._seg >= len(self.waypoints) - 1:
                if not self.loop:
                    return None
                self._seg = 0
            a, b = self.waypoints[self._seg], self.waypoints[self._seg + 1]
        return self._interp(a, b, self._progress)


def make_gps(serial_port: str | None, route_file: str | Path | None = None,
             origin: tuple[float, float] | None = None) -> SerialGPS | ReplayGPS:
    if serial_port:
        return SerialGPS(serial_port)
    routes_dir = Path(__file__).parent / "routes"
    route = route_file or (routes_dir / "route_01.json")
    if not Path(route).exists():
        raise FileNotFoundError(
            f"no GPS source: no serial port given and route file missing: {route}"
        )
    return ReplayGPS(route, origin=origin)
