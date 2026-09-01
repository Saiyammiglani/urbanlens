"""Fine-tune YOLOv8 on the urban-defect dataset. NOT RUN YET — scaffold only.

When a labelled dataset is ready (RDD 2022 + Roboflow pothole/garbage + custom):
    python train.py --data dataset.yaml --epochs 60
"""
import argparse


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="dataset.yaml")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--model", default="yolov8n.pt")  # nano for edge
    p.add_argument("--imgsz", type=int, default=640)
    args = p.parse_args()

    from ultralytics import YOLO  # noqa: import here so pipeline runs without it

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=16,
        project="runs",
        name="urbanlens",
    )
    print("done — best weights: runs/urbanlens/weights/best.pt")


if __name__ == "__main__":
    main()
