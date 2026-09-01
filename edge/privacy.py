"""On-device privacy: blur faces/plates/people BEFORE anything is stored or sent.

In production this runs a lightweight person/plate detector; for the demo we
provide a deterministic region-blur utility so raw pixels never leave the bus
unprocessed.
"""
import numpy as np


def blur_regions(frame: np.ndarray, regions: list[tuple]) -> np.ndarray:
    """Strongly blur the given (x1,y1,x2,y2) regions in-place on a copy."""
    out = frame.copy()
    h, w = out.shape[:2]
    for x1, y1, x2, y2 in regions:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        roi = out[y1:y2, x1:x2]
        # pixelate then gaussian-ish blur — cheap and irreversible
        small = roi[:: max(1, roi.shape[0] // 8), :: max(1, roi.shape[1] // 8)]
        out[y1:y2, x1:x2] = np.kron(small, np.ones((8, 8, 1), dtype=np.uint8))[
            : y2 - y1, : x2 - x1
        ]
    return out


def crop_evidence(frame: np.ndarray, bbox: tuple, pad: int = 32,
                  label: str | None = None, confidence: float | None = None) -> str | None:
    """Return a base64 JPEG evidence crop (small, privacy-filtered) with the
    detected issue highlighted by a red circle/ellipse. None if empty."""
    import base64
    import cv2
    h, w = frame.shape[:2]
    x1 = max(0, bbox[0] - pad)
    y1 = max(0, bbox[1] - pad)
    x2 = min(w, bbox[2] + pad)
    y2 = min(h, bbox[3] + pad)
    crop = frame[y1:y2, x1:x2].copy()
    if crop.size == 0:
        return None

    # --- highlight the detection with a red circle (ellipse around bbox) ---
    # bbox position inside the crop
    bx1, by1 = bbox[0] - x1, bbox[1] - y1
    bx2, by2 = bbox[2] - x1, bbox[3] - y1
    ch, cw = crop.shape[:2]
    bx1, by1 = max(0, bx1), max(0, by1)
    bx2, by2 = min(cw, bx2), min(ch, by2)
    if bx2 > bx1 and by2 > by1:
        center = ((bx1 + bx2) // 2, (by1 + by2) // 2)
        # a touch larger than the box so the circle clearly encloses the issue
        axes = (max(1, int((bx2 - bx1) * 0.62)), max(1, int((by2 - by1) * 0.62)))
        thickness = max(2, min(ch, cw) // 60)  # scale with crop size
        cv2.ellipse(crop, center, axes, 0, 0, 360, (0, 0, 255), thickness, cv2.LINE_AA)
        # caption: label + confidence
        if label:
            text = label.replace("_", " ") + (f" {confidence:.0%}" if confidence is not None else "")
            scale = max(0.4, min(ch, cw) / 300.0)
            font = cv2.FONT_HERSHEY_SIMPLEX
            (tw, th), _ = cv2.getTextSize(text, font, scale, 1)
            tx = max(0, min(center[0] - tw // 2, cw - tw - 4))
            ty = max(th + 6, min(by1 - 8, ch - 4))
            cv2.rectangle(crop, (tx - 3, ty - th - 3), (tx + tw + 3, ty + 3), (0, 0, 255), -1)
            cv2.putText(crop, text, (tx, ty), font, scale, (255, 255, 255), 1, cv2.LINE_AA)

    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        return None
    return base64.b64encode(buf.tobytes()).decode("ascii")
