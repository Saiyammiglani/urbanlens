"""Prepare the UrbanLens v1 training dataset.

Sources:
  - RDD2022 (India/Japan/Czech)  : Pascal VOC XMLs -> YOLO
      D20 -> pothole | D00/D01/D10/D11/D40 -> crack
  - keremberke garbage (HF)      : COCO json -> YOLO
      all 6 material classes -> garbage_dump

Output: ml/dataset/{images,labels}/{train,val} + dataset.yaml (3-class v1)
"""
import json
import random
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import zipfile

ROOT = Path(__file__).parent
DL = ROOT / "datasets" / "downloads"
OUT = ROOT / "dataset"
SEED = 42
VAL_FRACTION = 0.08
MAX_PER_SOURCE = 6000   # cap per source to keep laptop training tractable

RDD_CLASS_MAP = {
    "D20": 0,  # pothole
    "D00": 1, "D01": 1, "D10": 1, "D11": 1, "D40": 1,  # crack
}
GARBAGE_CLASS = 2  # garbage_dump


def voc_lines(tree, img_w: int, img_h: int) -> list[str]:
    lines = []
    for obj in tree.iter("object"):
        name = obj.find("name").text.strip()
        cls = RDD_CLASS_MAP.get(name)
        if cls is None:
            continue
        bb = obj.find("bndbox")
        x1, y1 = float(bb.find("xmin").text), float(bb.find("ymin").text)
        x2, y2 = float(bb.find("xmax").text), float(bb.find("ymax").text)
        if x2 <= x1 or y2 <= y1 or x1 >= img_w or y1 >= img_h:
            continue
        x2, y2 = min(x2, img_w), min(y2, img_h)
        cx = ((x1 + x2) / 2) / img_w
        cy = ((y1 + y2) / 2) / img_h
        lines.append(f"{cls} {cx:.6f} {cy:.6f} {(x2-x1)/img_w:.6f} {(y2-y1)/img_h:.6f}")
    return lines


def add_rdd_country(zip_path: Path, sink: list, keep_open: list):
    z = zipfile.ZipFile(zip_path)
    keep_open.append(z)
    members = z.namelist()
    xmls = sorted(m for m in members if "/train/annotations/xmls/" in m and m.endswith(".xml"))
    random.shuffle(xmls)
    count = 0
    for xm in xmls:
        if count >= MAX_PER_SOURCE:
            break
        base = Path(xm).stem
        img = next((m for m in members if m.endswith(f"/train/images/{base}.jpg")), None)
        if img is None:
            continue
        tree = ET.fromstring(z.read(xm))
        size = tree.find("size")
        w, h = int(size.find("width").text), int(size.find("height").text)
        lines = voc_lines(tree, w, h)
        if not lines:
            continue
        sink.append((z, img, lines))
        count += 1
    print(f"{zip_path.name}: kept {count} annotated images")


def add_garbage(zip_path: Path, sink: list, keep_open: list):
    z = zipfile.ZipFile(zip_path)
    keep_open.append(z)
    coco = json.loads(z.read("_annotations.coco.json"))
    img_by_id = {i["id"]: i for i in coco["images"]}
    anns_by_img: dict = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)
    names = set(z.namelist())
    ids = [i for i in img_by_id if i in anns_by_img]
    random.shuffle(ids)
    count = 0
    for iid in ids:
        if count >= MAX_PER_SOURCE:
            break
        info = img_by_id[iid]
        w, h = info["width"], info["height"]
        lines = []
        for a in anns_by_img[iid]:
            x, y, bw, bh = a["bbox"]
            if bw <= 0 or bh <= 0 or x >= w or y >= h:
                continue
            cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
            lines.append(f"{GARBAGE_CLASS} {cx:.6f} {cy:.6f} "
                         f"{min(bw, w - x) / w:.6f} {min(bh, h - y) / h:.6f}")
        if not lines:
            continue
        member = next((m for m in names if m.endswith("/" + info["file_name"])
                       or m == info["file_name"]), None)
        if member is None:
            continue
        sink.append((z, member, lines))
        count += 1
    print(f"{zip_path.name}: kept {count} annotated images")


def flush(sink: list, split: str) -> int:
    (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
    for i, (z, member, lines) in enumerate(sink):
        stem = Path(member).stem[:80] + f"_{i:06d}"
        ext = Path(member).suffix.lower() or ".jpg"
        (OUT / "images" / split / (stem + ext)).write_bytes(z.read(member))
        (OUT / "labels" / split / (stem + ".txt")).write_text("\n".join(lines))
    return len(sink)


def main():
    random.seed(SEED)
    if OUT.exists():
        shutil.rmtree(OUT)

    train_sink, val_sink, keep_open = [], [], []
    add_garbage(DL / "garbage_train.zip", train_sink, keep_open)
    add_garbage(DL / "garbage_valid.zip", val_sink, keep_open)

    rdd_sink = []
    for name in ("India_RDD.zip", "Japan_RDD.zip", "Czech_RDD.zip"):
        p = DL / name
        if p.exists():
            add_rdd_country(p, rdd_sink, keep_open)
        else:
            print(f"!! missing {name} — skipped")
    random.shuffle(rdd_sink)
    n_val = int(len(rdd_sink) * VAL_FRACTION)
    val_sink.extend(rdd_sink[:n_val])
    train_sink.extend(rdd_sink[n_val:])

    ntr = flush(train_sink, "train")
    nva = flush(val_sink, "val")
    print(f"\ndataset written: train={ntr} val={nva} -> {OUT}")

    (ROOT / "dataset.yaml").write_text(
        f"path: {OUT.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 3\n"
        "names: [pothole, crack, garbage_dump]\n"
    )
    print("dataset.yaml written")

    for z in keep_open:
        z.close()

    c = Counter()
    for f in (OUT / "labels").rglob("*.txt"):
        for line in f.read_text().splitlines():
            c[int(line.split()[0])] += 1
    print("label distribution:", dict(c))


if __name__ == "__main__":
    main()
