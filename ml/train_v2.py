"""UrbanLens v2 training run — 9 classes, RTX 5060 laptop (8 GB VRAM) tuned.

Usage:
    python train_v2.py                    # defaults: yolov8s, 30 epochs
    python train_v2.py --resume           # resume from last checkpoint
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).parent
WEIGHTS = {"n": "yolov8n.pt", "s": "yolov8s.pt", "m": "yolov8m.pt"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=WEIGHTS, default="s")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()

    run_name = "urbanlens_v2"
    if args.resume:
        import glob
        lasts = sorted(glob.glob(str(ROOT / "runs" / f"{run_name}*" / "weights" / "last.pt")))
        if not lasts:
            raise SystemExit("nothing to resume")
        model = YOLO(lasts[-1])
        results = model.train(resume=True)
    else:
        model = YOLO(WEIGHTS[args.model])
        results = model.train(
            data=str(ROOT / "dataset_v2.yaml"),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=4,          # Windows-safe dataloader workers
            device=0,
            project=str(ROOT / "runs"),
            name=run_name,
            patience=10,
            cache=False,
            augment=True,
            mosaic=1.0,
            degrees=5.0,
            translate=0.05,
            scale=0.4,
            fliplr=0.5,
            hsv_h=0.015, hsv_s=0.5, hsv_v=0.4,
            mixup=0.1,
            copy_paste=0.0,
            erasing=0.0,
        )
    metrics = results.results_dict if hasattr(results, "results_dict") else {}
    print("\n=== FINAL METRICS ===")
    for k, v in metrics.items():
        print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")
    best = ROOT / "runs" / run_name / "weights" / "best.pt"
    print(f"\nbest weights: {best}")


if __name__ == "__main__":
    main()
