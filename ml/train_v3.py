"""UrbanLens v3 training — fine-tune v2 with hard negatives (leaves/clutter).

Fine-tunes from v2 best.pt (already converged on 24.7k images) for a few
epochs over dataset_v3 = v2 + mined hard-negative street frames. The
negatives teach the model that leaves / roadside litter / general Indian
street clutter are NOT garbage_dump.

RTX 5060 8GB: ~35-45 min for 15 epochs.

Usage:
    python train_v3.py                # default: 15 epochs from v2 best
    python train_v3.py --epochs 25
    python train_v3.py --resume
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).parent
V2_BEST = ROOT / "runs" / "urbanlens_v2" / "weights" / "best.pt"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()

    if args.resume:
        import glob
        lasts = sorted(glob.glob(str(ROOT / "runs" / "urbanlens_v3*" / "weights" / "last.pt")))
        if not lasts:
            raise SystemExit("nothing to resume")
        model = YOLO(lasts[-1])
        model.train(resume=True)
        return

    if not V2_BEST.exists():
        raise SystemExit(f"v2 weights missing: {V2_BEST}")
    if not (ROOT / "dataset_v3.yaml").exists():
        raise SystemExit("dataset_v3 not prepared — run: python prepare_dataset_v3.py")

    model = YOLO(str(V2_BEST))
    model.train(
        data=str(ROOT / "dataset_v3.yaml"),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=4,            # Windows-safe dataloader workers
        lr0=0.001,            # LOW lr: gentle fine-tune, don't forget v2
        patience=8,
        project=str(ROOT / "runs"),
        name="urbanlens_v3",
        exist_ok=True,
        device=0,
        cache="disk",
    )
    print("\n[v3] training done — export with:")
    print("     python export_onnx.py --weights runs/urbanlens_v3/weights/best.pt")
    print("     then restart the edge agent to hot-swap the model")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    main()
