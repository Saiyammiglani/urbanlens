# -*- coding: utf-8 -*-
"""Prepare ANPR plate-detection dataset (Kaggle: indian-license-plates-with-labels).

2083 real Indian street images, YOLO format, single class 'plate'.
Splits 90/10 train/val. Free dataset, trained locally on the RTX 5060.
"""
import random
import shutil
from pathlib import Path

SRC = Path(__file__).parent / "anpr_data"
DST = Path(__file__).parent / "dataset_anpr"

random.seed(42)

imgs = sorted((SRC / "images").glob("*.*"))
pairs = []
for img in imgs:
    lab = SRC / "labels" / (img.stem + ".txt")
    if lab.exists() and lab.read_text().strip():
        pairs.append((img, lab))

random.shuffle(pairs)
n_val = max(1, len(pairs) // 10)
splits = {"train": pairs[n_val:], "val": pairs[:n_val]}

for split, items in splits.items():
    (DST / "images" / split).mkdir(parents=True, exist_ok=True)
    (DST / "labels" / split).mkdir(parents=True, exist_ok=True)
    for img, lab in items:
        shutil.copy2(img, DST / "images" / split / img.name)
        shutil.copy2(lab, DST / "labels" / split / lab.name)
    print(f"{split}: {len(items)} images")

yaml = DST / "dataset.yaml"
yaml.write_text(
    f"path: {DST}\ntrain: images/train\nval: images/val\n\nnc: 1\nnames: ['plate']\n"
)
print(f"dataset.yaml -> {yaml}")
print("train with: python train_plate.py")
