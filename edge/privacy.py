"""On-device privacy: pixelate faces/plates/people BEFORE anything is stored or sent.

Used on every evidence crop: pedestrian detections from the COCO model are
irreversibly pixelated inside the crop, so bystanders never leave the device
identifiable. Raw video never leaves the bus at all.
"""
import cv2
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
        # pixelate: downscale to ~8px cells then upscale back — cheap and irreversible
        rh, rw = roi.shape[:2]
        if rh < 2 or rw < 2:
            continue
        small = cv2.resize(roi, (max(1, rw // 8), max(1, rh // 8)),
                           interpolation=cv2.INTER_LINEAR)
        out[y1:y2, x1:x2] = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
    return out


def crop_evidence(frame: np.ndarray, bbox: tuple, pad: int = 32,
                  label: str | None = None, confidence: float | None = None,
                  blur_boxes: list[tuple] | None = None) -> str | None:
    """Return a base64 JPEG evidence crop (small, privacy-filtered) with the
    detected issue highlighted by a red circle/ellipse. None if empty.

    blur_boxes: frame-coordinate boxes (e.g. pedestrian detections) that are
    irreversibly pixelated inside the crop before encoding — bystanders never
    leave the device identifiable."""
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

    # --- privacy: pixelate bystanders (person boxes) inside the crop ---
    if blur_boxes:
        ch, cw = crop.shape[:2]
        regions = []
        for (px1, py1, px2, py2) in blur_boxes:
            # expand a little — faces/bodies at box edges stay covered
            ex = int((px2 - px1) * 0.15) + 6
            ey = int((py2 - py1) * 0.15) + 6
            rx1, ry1 = int(px1 - ex) - x1, int(py1 - ey) - y1   # → crop coords
            rx2, ry2 = int(px2 + ex) - x1, int(py2 + ey) - y1
            rx1, ry1 = max(0, rx1), max(0, ry1)
            rx2, ry2 = min(cw, rx2), min(ch, ry2)
            if rx2 > rx1 and ry2 > ry1:
                regions.append((rx1, ry1, rx2, ry2))
        crop = blur_regions(crop, regions)

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
