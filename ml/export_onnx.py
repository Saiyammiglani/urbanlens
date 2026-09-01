"""Export trained YOLO weights to ONNX for on-bus inference (edge/detector.py).

    ml/venv/Scripts/python export_onnx.py --weights runs/urbanlens_v1/weights/best.pt

Writes model.onnx + model_labels.json (class order) next to it; the edge agent
auto-picks both up on next start.
"""
import argparse
import json
from pathlib import Path

EDGE_MODELS = Path(__file__).parent.parent / "edge" / "models"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--weights", required=True)
    p.add_argument("--out", default=str(EDGE_MODELS / "model.onnx"))
    args = p.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.weights)
    exported = model.export(format="onnx", imgsz=640, simplify=True, opset=12,
                            dynamic=False)
    src = Path(exported if not isinstance(exported, (list, tuple)) else exported[-1])
    EDGE_MODELS.mkdir(parents=True, exist_ok=True)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)
    (dest.with_name("model_labels.json")).write_text(
        json.dumps(list(model.names.values()))
    )
    print(f"exported -> {dest}")
    print(f"labels   -> {dest.with_name('model_labels.json')}: {list(model.names.values())}")
    print("edge/detector.py will auto-load these on next agent start")


if __name__ == "__main__":
    main()
