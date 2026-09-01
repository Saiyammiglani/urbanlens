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
