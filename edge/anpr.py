# -*- coding: utf-8 -*-
"""ANPR pipeline — real plate detection (trained YOLOv8) + RapidOCR.

Runs every Nth frame (plates don't move between frames), dedups by plate
text within a cooldown, and POSTs alerts to the backend traffic_alerts table.
Kind: 'anpr' (detections), 'stolen' (watchlist hit).
"""
import logging
import re
import threading
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("edge.anpr")

MODELS_DIR = Path(__file__).parent / "models"

# Indian plate format, e.g. DL01CJ8943, MH12AB1234, KL01BM5673
PLATE_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$")

# Watchlist — plates of interest (demo: swap for stolen-vehicle DB feed)
WATCHLIST = {"STOLEN01": "flagged vehicle (demo watchlist)"}


class ANPR:
    def __init__(self, backend_url: str, token: str, run_every: int = 5,
                 conf: float = 0.35, votes_needed: int = 3, vote_window: float = 12.0):
        import onnxruntime as ort
        self.run_every = run_every  # run every Nth call only
        self.conf = conf
        self._frame_no = 0
        self._cooldown = {}   # plate -> last alert time
        self._votes = {}      # track key -> [(plate, conf, t), ...]
        self._votes_needed = votes_needed
        self._vote_window = vote_window
        self._lock = threading.Lock()

        plate_onnx = MODELS_DIR / "plate.onnx"
        if plate_onnx.exists():
            so = ort.SessionOptions()
            so.inter_op_num_threads = 1
            so.intra_op_num_threads = 2
            self.sess = ort.InferenceSession(
                str(plate_onnx), so, providers=["CPUExecutionProvider"])
            self.input_name = self.sess.get_inputs()[0].name
            log.info("plate detector loaded: %s", plate_onnx.name)
        else:
            self.sess = None
            log.warning("plate.onnx missing — ANPR disabled")

        from rapidocr_onnxruntime import RapidOCR
        self.ocr = RapidOCR()

        self.url = backend_url.rstrip("/") + "/api/v1/traffic/anpr"
        self.headers = {"X-API-Token": token}

    # ---- plate detector -------------------------------------------------
    def _detect_plates(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        img = cv2.resize(frame_bgr, (640, 640))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)[None]
        out = self.sess.run(None, {self.input_name: img})[0]
        # out: [1, 4+1, N] -> transpose to [N, 5]; rows are cx,cy,w,h,score
        out = out[0].T if out.ndim == 3 else out
        raw = []
        h, w = frame_bgr.shape[:2]
        for row in out:
            cx, cy, bw, bh, score = row[:5]
            if score < self.conf:
                continue
            # cxcywh -> xyxy, then scale 640-space -> original frame
            x1 = int((cx - bw / 2) / 640 * w)
            y1 = int((cy - bh / 2) / 640 * h)
            x2 = int((cx + bw / 2) / 640 * w)
            y2 = int((cy + bh / 2) / 640 * h)
            raw.append((max(0, x1), max(0, y1), min(w, x2), min(h, y2), float(score)))
        if not raw:
            return []
        # greedy NMS (same as detector.py)
        arr = np.array(raw, dtype=np.float32)
        boxes, scores = arr[:, :4], arr[:, 4]
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
            order = order[1:][iou <= 0.45]
        return [raw[i] for i in keep]

    # ---- text normalisation ----------------------------------------------
    @staticmethod
    def _clean(text: str):
        """OCR text -> Indian plate format. Returns None if not plate-like."""
        t = text.upper()
        t = re.sub(r"[^A-Z0-9]", "", t)      # strip spaces, punctuation
        # state codes commonly confused
        for bad, good in (("0L", "OL"), ("1L", "IL"), ("D1", "DL")):
            if t.startswith(bad):
                t = good + t[len(bad):]
        if PLATE_RE.match(t):
            return t
        # OCR crops often include extra text (IND, etc.) — search inside
        m = re.search(r"[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}\b", t)
        return m.group(0) if m else None

    # ---- main entry ------------------------------------------------------
    def observe(self, frame_bgr, fix: dict):
        """Call once per frame; internally samples every run_every frames."""
        if self.sess is None:
            return
        self._frame_no += 1
        if self._frame_no % self.run_every:
            return

        try:
            boxes = self._detect_plates(frame_bgr)
        except Exception:
            log.exception("plate detection failed")
            return

        for (x1, y1, x2, y2, det_conf) in boxes[:2]:  # top-2 plates per frame
            crop = frame_bgr[max(0, y1):y2, max(0, x1):x2]
            if crop.size < 400:  # too small to OCR
                continue
            # upscale small crops for OCR accuracy
            if crop.shape[0] < 48:
                crop = cv2.resize(crop, None, fx=2, fy=2,
                                  interpolation=cv2.INTER_CUBIC)
            try:
                res, _ = self.ocr(crop)
            except Exception:
                continue
            if not res:
                continue
            # combine OCR fragments: filter junk (IND/INDIA/stars), then try
            # single fragments, x-sorted join (single-line plate), y-sorted join
            def is_junk(t):
                u = t.upper().strip()
                return (not u or u in {"IND", "INDIA"}
                        or not any(ch.isalnum() for ch in u))

            frags = [(r[1], float(r[2]), r[0]) for r in res
                     if r[1] and not is_junk(r[1])]
            candidates = [t for t, _, _ in frags]
            if len(frags) > 1:
                by_x = sorted(frags, key=lambda f: (f[2][0][0], f[2][0][1]))
                by_y = sorted(frags, key=lambda f: (f[2][0][1], f[2][0][0]))
                candidates += ["".join(t for t, _, _ in by_x),
                               "".join(t for t, _, _ in by_y),
                               " ".join(t for t, _, _ in by_x)]

            plate, ocr_conf = None, 0.0
            for cand in candidates:
                cleaned = self._clean(cand)
                if cleaned:
                    conf_c = max(c for _, c, _ in frags)
                    if conf_c > ocr_conf:
                        plate, ocr_conf = cleaned, conf_c
            if not plate:
                continue

            # ---- multi-frame voting ---------------------------------------
            # Track key: coarse plate position. A stationary camera or slow
            # relative motion keeps the key stable across frames.
            track_key = (x1 // 80, y1 // 80)
            now = time.time()
            with self._lock:
                reads = [(p, c, t) for (p, c, t) in self._votes.get(track_key, [])
                         if now - t < self._vote_window]
                reads.append((plate, ocr_conf, now))
                self._votes[track_key] = reads
                # drop stale tracks
                self._votes = {k: v for k, v in self._votes.items()
                               if v and now - v[-1][2] < self._vote_window * 2}

                if len(reads) < self._votes_needed:
                    continue
                # majority vote across reads
                counts = {}
                for p, c, t in reads:
                    counts.setdefault(p, []).append(c)
                best_plate = max(counts, key=lambda p: len(counts[p])
                                 + 0.1 * max(counts[p]))
                n_votes = len(counts[best_plate])
                if n_votes < self._votes_needed:
                    continue
                # fire once per track: consume the votes
                del self._votes[track_key]
                if now - self._cooldown.get(best_plate, 0) < 120:
                    continue  # same plate within 2 min: skip
                self._cooldown[best_plate] = now
                voted_conf = round(sum(counts[best_plate]) / n_votes, 3)

            conf = voted_conf
            combined_conf = round((det_conf * 0.4 + conf * 0.6), 3)

            kind = "anpr"
            notes = f"{n_votes}-frame vote"
            if best_plate in WATCHLIST:
                kind, notes = "stolen", WATCHLIST[best_plate]

            log.info("ANPR %s: %s (det %.2f, ocr %.2f, %d votes)",
                     kind, best_plate, det_conf, conf, n_votes)
            threading.Thread(
                target=self._upload, daemon=True,
                args=(best_plate, combined_conf, kind, fix, notes)).start()

    def _upload(self, plate, conf, kind, fix, notes):
        import requests
        payload = {
            "plate": plate, "plate_confidence": conf, "kind": kind,
            "vehicle_type": None, "lat": fix.get("lat"), "lon": fix.get("lon"),
            "notes": notes,
        }
        for attempt in (1, 2):
            try:
                r = requests.post(self.url, json=payload,
                                  headers=self.headers, timeout=12)
                if r.status_code == 200:
                    return
                log.warning("anpr upload %s: %s", r.status_code, r.text[:120])
            except requests.RequestException as exc:
                log.warning("anpr upload error: %s", exc)
            time.sleep(2 * attempt)
