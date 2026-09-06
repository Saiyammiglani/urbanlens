# -*- coding: utf-8 -*-
"""Train the ANPR plate detector — YOLOv8n, 1 class ('plate'), ~1-2h on RTX 5060.

Real data: 2083 labeled Indian street images (Kaggle free dataset).
Output: ml/runs/plate_detector/weights/best.pt -> export to edge/models/plate.onnx
"""
import argparse
from pathlib import Path

ML = Path(__file__).parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--model", default="yolov8n.pt")
    args = p.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=str(ML / "dataset_anpr" / "dataset.yaml"),
        epochs=args.epochs,
        imgsz=640,
        batch=32,
        device=0,           # RTX 5060
        project=str(ML / "runs"),
        name="plate_detector",
        patience=15,
        workers=4,
        close_mosaic=10,    # mosaic off at the end (same trick that boosted v3)
    )


if __name__ == "__main__":
    main()
