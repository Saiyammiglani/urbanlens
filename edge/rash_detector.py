# -*- coding: utf-8 -*-
"""Rash-driving detection — rule-based heuristics on COCO vehicle tracking.

Tracks vehicles across frames (greedy IoU matching, no external tracker
dependency), estimates relative motion, and flags:
  - speeders: sustained high relative displacement (pixels/sec vs fleet norm)
  - weavers:  direction changes / lateral zig-zag above threshold
When flagged and a plate is available from ANPR, an alert is emitted with
plate + confidence + GPS + timestamp (PS requirement).
"""
import logging
import threading
import time

import numpy as np

log = logging.getLogger("edge.rash")

# tunables (pixel-space; camera looks forward from the bus)
TRACK_LOST_SEC = 1.5          # drop track if unseen this long
SPEED_HISTORY = 6             # frames of speed history per track
SPEED_FACTOR = 2.0            # flag if speed > factor * fleet median
MIN_TRACK_LEN = 5             # need this many observations before judging
DIRECTION_CHANGES = 3         # >= this many lateral sign flips = weaving
MIN_PIXEL_SPEED = 25.0        # ignore near-stationary relative motion


class RashDetector:
    def __init__(self, backend_url: str, token: str, cooldown: float = 300.0):
        self.tracks = {}          # tid -> dict(boxes, times, speeds, dirs)
        self._next_id = 1
        self._alerted = {}        # tid -> time
        self._cooldown = cooldown
        self.url = backend_url.rstrip("/") + "/api/v1/traffic/anpr"
        self.headers = {"X-API-Token": token}

    # ---- tracking ---------------------------------------------------------
    def _match(self, boxes):
        """Greedy IoU match of detections to existing tracks.
        boxes: [(x1,y1,x2,y2,kind)] -> {(x1,y1,x2,y2,kind): tid|None}"""
        import cv2
        assignments = {}
        tids = list(self.tracks)
        for box in boxes:
            x1, y1, x2, y2, kind = box
            best_iou, best_tid = 0.3, None
            for tid in tids:
                tr = self.tracks[tid]["last_box"]
                xx1 = max(x1, tr[0]); yy1 = max(y1, tr[1])
                xx2 = min(x2, tr[2]); yy2 = min(y2, tr[3])
                inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
                a1 = (x2 - x1) * (y2 - y1)
                a2 = (tr[2] - tr[0]) * (tr[3] - tr[1])
                iou = inter / (a1 + a2 - inter + 1e-9)
                if iou > best_iou:
                    best_iou, best_tid = iou, tid
            if best_tid is not None:
                tids.remove(best_tid)
            assignments[box] = best_tid
        return assignments

    # ---- main entry -------------------------------------------------------
    def observe(self, vehicles, now: float | None = None):
        """vehicles: list of (x1, y1, x2, y2, class_name) from the COCO
        detector. Call once per processed frame."""
        now = time.time() if now is None else now
        if not vehicles:
            return
        assigns = self._match(list(vehicles))

        # fleet median speed this frame (context: everyone is moving?)
        frame_speeds = []
        for box, tid in assigns.items():
            if tid is not None:
                tr = self.tracks[tid]
                dt = now - tr["last_t"]
                if dt > 0.05:
                    cx_new = (box[0] + box[2]) / 2
                    cx_old = (tr["last_box"][0] + tr["last_box"][2]) / 2
                    cy_new = (box[1] + box[3]) / 2
                    cy_old = (tr["last_box"][1] + tr["last_box"][3]) / 2
                    spd = ((cx_new - cx_old) ** 2 + (cy_new - cy_old) ** 2) ** 0.5 / dt
                    frame_speeds.append(spd)
        fleet_median = float(np.median(frame_speeds)) if frame_speeds else 0.0

        for box, tid in assigns.items():
            x1, y1, x2, y2, kind = box
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = {"boxes": [], "times": [], "speeds": [],
                                    "dirs": [], "last_box": box, "last_t": now}
                continue
            tr = self.tracks[tid]
            dt = now - tr["last_t"]
            if dt <= 0.05:
                continue
            cx_new, cy_new = (x1 + x2) / 2, (y1 + y2) / 2
            cx_old = (tr["last_box"][0] + tr["last_box"][2]) / 2
            cy_old = (tr["last_box"][1] + tr["last_box"][3]) / 2
            dx, dy = cx_new - cx_old, cy_new - cy_old
            spd = (dx ** 2 + dy ** 2) ** 0.5 / dt

            tr["boxes"].append(box)
            tr["times"].append(now)
            tr["speeds"].append(spd)
            tr["dirs"].append(float(np.sign(dx)))
            tr["last_box"], tr["last_t"] = box, now

            if len(tr["speeds"]) < MIN_TRACK_LEN:
                continue
            if tid in self._alerted and now - self._alerted[tid] < self._cooldown:
                continue

            speeds = tr["speeds"][-SPEED_HISTORY:]
            avg_spd = float(np.mean(speeds))
            reasons = []
            # speeding relative to fleet
            if avg_spd > max(MIN_PIXEL_SPEED, fleet_median * SPEED_FACTOR
                             if fleet_median > 10 else 0):
                reasons.append(f"speed {avg_spd:.0f}px/s vs fleet {fleet_median:.0f}")
            # weaving: lateral direction flips
            dirs = [d for d in tr["dirs"][-(SPEED_HISTORY * 2):] if d != 0]
            flips = sum(1 for a, b in zip(dirs, dirs[1:]) if a != b)
            if flips >= DIRECTION_CHANGES:
                reasons.append(f"{flips} lane changes in {len(dirs)} frames")

            if reasons:
                self._alerted[tid] = now
                log.info("RASH DRIVING tid=%d %s %s", tid, kind, "; ".join(reasons))
                return {  # caller (agent) attaches plate from ANPR + uploads
                    "track_id": tid, "vehicle_type": kind,
                    "reasons": reasons, "avg_speed_px_s": round(avg_spd, 1),
                    "fleet_median_px_s": round(fleet_median, 1),
                }

        # drop stale tracks
        stale = [t for t, tr in self.tracks.items()
                 if now - tr["last_t"] > TRACK_LOST_SEC]
        for t in stale:
            del self.tracks[t]
        return None

    def upload(self, fix: dict, evidence: dict, plate: str | None = None,
               plate_conf: float | None = None):
        import requests
        payload = {
            "kind": "rash_driving",
            "plate": plate, "plate_confidence": plate_conf,
            "vehicle_type": evidence.get("vehicle_type"),
            "lat": fix.get("lat"), "lon": fix.get("lon"),
            "notes": "; ".join(evidence.get("reasons", [])),
        }
        try:
            r = requests.post(self.url, json=payload, headers=self.headers,
                              timeout=12)
            if r.status_code == 200:
                log.info("rash-driving alert uploaded")
            else:
                log.warning("rash upload %s: %s", r.status_code, r.text[:120])
        except requests.RequestException as exc:
            log.warning("rash upload error: %s", exc)
