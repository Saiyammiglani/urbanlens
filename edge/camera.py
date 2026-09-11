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

        File sources are DECODE-STRIDED: a 60 fps video paced at 5 fps would
        otherwise play at 1/12th speed (every frame read sequentially). For
        files we grab-and-discard frames so the effective sampling equals
        EDGE_FILE_FPS (default 10 — 2x the designed 5 fps operating point, so
        detection gates, streak windows and tracking all behave identically)
        while wall-clock time drops proportionally. Webcams are never strided.
        """
        import os
        self.source = source
        self.fps_cap = fps_cap
        self._frame_id = 0
        self._cap = cv2.VideoCapture(int(source) if isinstance(source, str) and source.isdigit() else source)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open video source: {source}")
        self._interval = 1.0 / max(fps_cap, 0.1)
        self._last = 0.0
        # decode stride for file sources (webcam/live streams: always 1)
        self._stride = 1
        if not (isinstance(source, int) or (isinstance(source, str) and source.isdigit())):
            vfps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            target = float(os.getenv("EDGE_FILE_FPS", "0"))
            # EDGE_FILE_FPS=0 (default): process as fast as compute allows;
            # the pacing cap only makes sense for live cameras. A positive
            # value sets a fixed effective sampling rate instead.
            self._stride = 1
            if target > 0:
                self._stride = max(1, round(vfps / target))
                self._interval = 1.0 / target
            else:
                # sample every ~0.1s of footage regardless of video fps —
                # dense enough for streak/vote gates, bounded decode cost
                self._stride = max(1, round(vfps / 10.0))
                self._interval = 0.0  # no pacing: wall time = compute time
            if self._stride > 1:
                print(f"[camera] file source: stride {self._stride} "
                      f"({vfps:.0f} fps video -> {vfps/self._stride:.0f} fps effective)")

    def read(self) -> Frame | None:
        """Return next frame honouring fps_cap, or None when source ends."""
        now = time.time()
        if now - self._last < self._interval:
            time.sleep(self._interval - (now - self._last))
        self._last = time.time()
        self._frame_id += 1

        for _ in range(self._stride - 1):     # decode-discard skipped frames
            if not self._cap.grab():
                return None
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
