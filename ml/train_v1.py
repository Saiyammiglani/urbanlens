"""UrbanLens v1 training run — RTX 5060 laptop (8 GB VRAM) tuned.

Usage:
    python train_v1.py                    # defaults: yolov8s, 30 epochs
    python train_v1.py --model n --epochs 40
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

    if args.resume:
        import glob
        lasts = sorted(glob.glob(str(ROOT / "runs" / "urbanlens_v1*" / "weights" / "last.pt")))
        if not lasts:
            raise SystemExit("nothing to resume")
        model = YOLO(lasts[-1])
        results = model.train(resume=True)
    else:
        model = YOLO(WEIGHTS[args.model])
        results = model.train(
            data=str(ROOT / "dataset.yaml"),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=4,          # Windows-safe dataloader workers
            device=0,
            project=str(ROOT / "runs"),
            name="urbanlens_v1",
            patience=10,
            cache=False,        # 24GB RAM — disk cache off to be safe
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
    best = ROOT / "runs" / "urbanlens_v1" / "weights" / "best.pt"
    print(f"\nbest weights: {best}")


if __name__ == "__main__":
    main()
