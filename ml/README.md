# ML Pipeline — v1 COMPLETE ✅

## Final model (trained 2026-08-31, RTX 5060 Laptop)

- `runs/urbanlens_v1/weights/best.pt` — YOLOv8s, 30 epochs, 640px
- **Final validation: mAP50 0.625 · mAP50-95 0.384 · P 0.694 · R 0.555**
- Exported ONNX (44.7 MB) deployed at `edge/models/model.onnx` + `model_labels.json`
- Edge CPU inference: **~9 FPS** (109 ms/frame) — verified live end-to-end
- Live test: garbage 0.85–0.94 conf, cracks 0.46–0.59 conf (hardest class)
## Environment
- Python 3.12 venv at `ml/venv`
- torch 2.11.0+cu128 (RTX 5060 Laptop / Blackwell sm_120 verified working)
- ultralytics 8.4.135, onnx, onnxruntime

## Datasets (downloaded & merged)
| Source | Classes | Images kept |
|---|---|---|
| keremberke/garbage-object-detection (HF) | garbage_dump (6 mats merged) | 8,098 |
| RDD2022 India (figshare range-fetch) | pothole, crack | 3,318 |
| RDD2022 Japan (figshare range-fetch) | pothole, crack | 6,000 |
| RDD2022 Czech (figshare range-fetch) | pothole, crack | 1,072 |
| **Total** | 3 classes | **15,559 train / 2,929 val** |

Note: RDD2022's original S3 bucket is access-denied; we range-fetch the 3 needed
country zips out of the 13.2 GB FigShare wrapper zip (`fetch_rdd_chunks.py`) —
saves ~11 GB.

## v1 taxonomy (3 classes — real model)
- 0: pothole  (RDD D20)
- 1: crack    (RDD D00/D01/D10/D11/D40)
- 2: garbage_dump (all keremberke classes merged)

Remaining 6 platform classes (waterlogging, illegal_parking, broken_streetlight,
open_manhole, roadside_debris, faded_signage) stay on the mock detector until
v2 data is sourced (needs a free Roboflow API key or manual annotation).

## Pipeline commands
```
ml/venv/Scripts/python prepare_dataset.py    # rebuild ml/dataset + dataset.yaml
ml/venv/Scripts/python train_v1.py           # yolov8s, 30 epochs, batch 16
ml/venv/Scripts/python train_v1.py --model n --epochs 40
ml/venv/Scripts/python train_v1.py --resume  # resume interrupted run
ml/venv/Scripts/python export_onnx.py --weights runs/urbanlens_v1/weights/best.pt
```
Then drop the ONNX at `edge/models/model.onnx` — the edge agent auto-switches
from mock to real inference on next start.

## Expected timings (RTX 5060 8GB, ~19k train imgs, 640px, batch 16)
- yolov8s / 30 epochs ≈ 4–6 h (overnight run recommended)
- yolov8n / 30 epochs ≈ 2–3 h

---

# v2 model (CURRENT) — 9 classes, 24.7k images

Built from 12 open Roboflow datasets (CC BY 4.0 / Public Domain):
`ml/prepare_dataset_v2.py` → `ml/dataset_v2/` (24,771 train / 3,951 val).

Classes & box counts: pothole 8,848 · crack 14,471 · garbage_dump 61,522 ·
waterlogging 10,064 · open_manhole 1,946 · broken_streetlight 3,002 ·
roadside_debris 4,482 · faded_signage 562 · illegal_parking 736.

## Final metrics (YOLOv8s, 30 epochs, RTX 5060, ~2.5 h)
- **Overall: mAP50 0.666 · mAP50-95 0.446 · P 0.730 · R 0.622**

| Class | mAP50 | mAP50-95 | Notes |
|---|---|---|---|
| open_manhole | 0.992 | 0.936 | excellent |
| illegal_parking | 0.984 | 0.866 | carpark-context data; strong but biased domain |
| broken_streetlight | 0.741 | 0.342 | poles generally, not only broken ones |
| faded_signage | 0.720 | 0.449 | only 562 boxes |
| pothole | 0.686 | ~0.39 | vs v1 0.71 (3-class model) |
| garbage_dump | 0.629 | 0.379 | dominant class (61k boxes) |
| waterlogging | 0.481 | 0.322 | varied definitions across sources |
| crack | 0.453 | ~0.18 | hardest class (thin objects) |
| roadside_debris | 0.309 | 0.146 | weakest; experimental |

vs v1 (3 classes): mAP50 0.666 vs 0.625 — better overall score with 3× classes.

## Pipeline commands (v2)
```
ml/venv/Scripts/python prepare_dataset_v2.py          # rebuild ml/dataset_v2
ml/venv/Scripts/python train_v2.py                    # 30 epochs
ml/venv/Scripts/python train_v2.py --resume           # resume interrupted run
ml/venv/Scripts/python export_onnx.py --weights runs/urbanlens_v2/weights/best.pt
```
Deployed: `edge/models/model.onnx` + `model_labels.json` (9 labels) — edge agent
auto-loads both on start; verified live (garbage_dump @ 0.83–0.91 conf).
