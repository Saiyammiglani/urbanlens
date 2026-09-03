"""Prepare v3 dataset: v2 + hard negatives mined from our own street footage.

The v2 model's worst real-world failure: leaves/roadside clutter detected as
garbage_dump (fires 0.40-0.76 on clutter, 0.80-0.95 on real dumps).

Fix strategy — hard-negative mining:
  * Sample frames from edge/media/*.mp4 (Indian street footage, domain-matched)
  * Keep frames where the CURRENT model fires only weakly (all dets < 0.65)
    -> these are exactly the "leaves/clutter" frames that confuse the model
  * Add them as background images (image with an EMPTY label file)
  * Frames with stronger detections are EXCLUDED so no real object gets
    taught as background.

Also adds: horizontal flips of the negatives (free 2x).

Output: dataset_v3/ (v2 images are HARD-LINKED, no extra disk space),
        dataset_v3.yaml
"""
import shutil
import sys
from pathlib import Path

import cv2

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
V2 = ROOT / "dataset_v2"
V3 = ROOT / "dataset_v3"
MEDIA = ROOT.parent / "edge" / "media"
NEG_RAW_CONF = 0.65   # frame is a negative only if NO detection reaches this
SAMPLE_EVERY_S = 1.0  # sample one frame per second of footage
MAX_NEGS = 1200       # cap: negatives should stay ~5% of the dataset


def find_model() -> Path:
    here = ROOT / "runs" / "urbanlens_v2" / "weights" / "best.pt"
    if here.exists():
        return here
    raise SystemExit("v2 weights not found — expected runs/urbanlens_v2/weights/best.pt")


def clone_v2():
    """Hard-link v2 train/val images+labels into dataset_v3 (no disk cost)."""
    for split in ("train", "val"):
        (V3 / "images" / split).mkdir(parents=True, exist_ok=True)
        (V3 / "labels" / split).mkdir(parents=True, exist_ok=True)
        for src in (V2 / "images" / split).iterdir():
            dst = V3 / "images" / split / src.name
            if not dst.exists():
                try:
                    import os
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)  # fallback (different volume)
        for src in (V2 / "labels" / split).iterdir():
            dst = V3 / "labels" / split / src.name
            if not dst.exists():
                try:
                    import os
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
    n_train = len(list((V3 / "images" / "train").iterdir()))
    n_val = len(list((V3 / "images" / "val").iterdir()))
    print(f"[v3] cloned v2 via hardlinks: train={n_train} val={n_val}")


def mine_negatives():
    from ultralytics import YOLO

    model = YOLO(str(find_model()))
    videos = sorted(MEDIA.glob("*.mp4"))
    if not videos:
        raise SystemExit("no videos in edge/media/")
    print(f"[v3] mining hard negatives from: {[v.name for v in videos]}")

    kept = 0
    out_dir = V3 / "images" / "train"
    lbl_dir = V3 / "labels" / "train"
    for vid in videos:
        cap = cv2.VideoCapture(str(vid))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, int(fps * SAMPLE_EVERY_S))
        i = 0
        while kept < MAX_NEGS:
            ok, frame = cap.read()
            if not ok:
                break
            i += 1
            if i % step != 0:
                continue
            # run raw inference; a frame qualifies as negative if nothing
            # fires confidently (leaves fire 0.4-0.6, real objects 0.7+)
            results = model.predict(frame, conf=NEG_RAW_CONF, verbose=False, imgsz=640)
            if len(results[0].boxes) > 0:
                continue  # something real in frame — skip, don't mislabel it
            name = f"neg_{vid.stem}_{i:06d}"
            cv2.imwrite(str(out_dir / f"{name}.jpg"), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 85])
            (lbl_dir / f"{name}.txt").touch()  # empty label = background image
            kept += 1
        cap.release()
        print(f"[v3]   {vid.name}: negatives so far = {kept}")
        if kept >= MAX_NEGS:
            break

    # horizontal flips of half the negatives (free augmentation, still clean)
    negs = sorted(out_dir.glob("neg_*.jpg"))
    for p in negs[: len(negs) // 2]:
        img = cv2.imread(str(p))
        if img is None:
            continue
        cv2.imwrite(str(out_dir / f"flip_{p.name}"), cv2.flip(img, 1),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
        (lbl_dir / f"flip_{p.stem}.txt").touch()
    print(f"[v3] mined {kept} hard negatives (+{len(negs)//2} flips)")


def write_yaml():
    yaml_text = f"""path: {V3}
train: images/train
val: images/val

nc: 9
names: ['pothole', 'crack', 'garbage_dump', 'waterlogging', 'open_manhole', 'broken_streetlight', 'roadside_debris', 'faded_signage', 'illegal_parking']
"""
    (ROOT / "dataset_v3.yaml").write_text(yaml_text)
    print(f"[v3] wrote dataset_v3.yaml")


if __name__ == "__main__":
    if not (ROOT / "dataset_v3.yaml").exists():
        clone_v2()
        mine_negatives()
        write_yaml()
        print("[v3] done — run: python train_v3.py")
    else:
        print("[v3] dataset_v3.yaml already exists — delete it to re-run")
