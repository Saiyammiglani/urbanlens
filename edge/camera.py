"""Camera / video source abstraction.

Works with: live webcam index, recorded route video (for demos/replays), or a
plain image folder. Always yields (frame_bgr, frame_id, timestamp_iso).
Real sources only — no synthetic frames.
"""
import time
from dataclasses import dataclass
from pathlib import Path

import cv2


@dataclass
class Frame:
    image: object          # numpy BGR array
    frame_id: int
    timestamp: float       # unix seconds


class CameraSource:
    def __init__(self, source: str | int = 0, fps_cap: float = 5.0):
        """
        source: webcam index (int or digit-string) or a video file path.
        fps_cap: cap the processing rate to save edge CPU/battery.
        """
        self.source = source
        self.fps_cap = fps_cap
        self._frame_id = 0
        self._cap = cv2.VideoCapture(int(source) if isinstance(source, str) and source.isdigit() else source)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open video source: {source}")
        self._interval = 1.0 / max(fps_cap, 0.1)
        self._last = 0.0

    def read(self) -> Frame | None:
        """Return next frame honouring fps_cap, or None when source ends."""
        now = time.time()
        if now - self._last < self._interval:
            time.sleep(self._interval - (now - self._last))
        self._last = time.time()
        self._frame_id += 1

        ok, img = self._cap.read()
        if not ok:
            return None  # end of video / stream glitch
        return Frame(img, self._frame_id, time.time())

    def release(self):
        self._cap.release()


def find_demo_video() -> str | None:
    """Look for a route video dropped into edge/media/."""
    media = Path(__file__).parent / "media"
    if media.exists():
        vids = sorted(p for p in media.iterdir() if p.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"})
        return str(vids[0]) if vids else None
    return None
