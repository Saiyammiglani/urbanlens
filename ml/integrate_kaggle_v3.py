"""Integration of real-world Kaggle datasets into dataset_v3.

Called from prepare_dataset_v3.py. Each source is credited, license-checked,
and mapped onto the 9-class UrbanLens scheme.

Sources:
  roaddamage  sabidrahman/pothole-cracks-and-openmanhole
              YOLO ids 0=pothole 1=crack 2=open_manhole; good_road negatives
  garbage     viswaprakash1990/garbage-detection (CC BY 4.0)
              6 material classes -> garbage_dump
  crack_neg   arunrk7/surface-crack-detection (CC BY)
              6k Negative concrete images + 1.5k Positive crack patches
  taco        TACO (CC BY 4.0), 18 litter classes -> garbage_dump

v3 class map: 0 pothole, 1 crack, 2 garbage_dump, 3 waterlogging,
              4 open_manhole, 5 broken_streetlight, 6 roadside_debris,
              7 faded_signage, 8 illegal_parking
"""
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V3 = ROOT / "dataset_v3"
KAGGLE = ROOT / "datasets" / "kaggle"

C_POTHOLE, C_CRACK, C_GARBAGE, C_WATERLOG, C_MANHOLE = 0, 1, 2, 3, 4


def _link(src: Path, dst: Path):
    if dst.exists():
        return
    try:
        import os
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _remap_label(lbl: Path, mapping: dict) -> str:
    """Read a YOLO label file, remap class ids, return text (may be empty)."""
    lines = []
    for l in lbl.read_text().splitlines():
        parts = l.split()
        if len(parts) != 5:
            continue
        try:
            cid = int(float(parts[0]))
        except ValueError:
            continue
        if cid in mapping:
            lines.append(" ".join([str(mapping[cid])] + parts[1:]))
    return "\n".join(lines) + ("\n" if lines else "")


def add_roaddamage():
    base = KAGGLE / "roaddamage" / "dataset" / "dataset"
    if not (base / "train" / "images").exists():
        print("[v3] roaddamage not found — skipping")
        return 0
    mapping = {0: C_POTHOLE, 1: C_CRACK, 2: C_MANHOLE}
    n = 0
    for split, out_split in (("train", "train"), ("valid", "val")):
        img_dir, lbl_dir = base / split / "images", base / split / "labels"
        if not img_dir.exists():
            continue
        for img in img_dir.glob("*.jpg"):
            lbl = lbl_dir / (img.stem + ".txt")
            if not lbl.exists():
                continue
            stem = f"kd_{split}_{img.stem}"
            out_lbl = V3 / "labels" / out_split / (stem + ".txt")
            if not out_lbl.exists():
                out_lbl.write_text(_remap_label(lbl, mapping))
            _link(img, V3 / "images" / out_split / (stem + ".jpg"))
            n += 1
    # good_road folder = clean-road background negatives
    good = base / "classes" / "good_road" / "images"
    if good.exists():
        for img in good.glob("*.jpg"):
            stem = f"kd_good_{img.stem}"
            (V3 / "labels" / "train" / (stem + ".txt")).touch()
            _link(img, V3 / "images" / "train" / (stem + ".jpg"))
            n += 1
    print(f"[v3] roaddamage: +{n} images (pothole/crack/open_manhole + negatives)")
    return n


def add_garbage():
    base = KAGGLE / "garbage" / "GARBAGE CLASSIFICATION"
    if not (base / "train" / "images").exists():
        print("[v3] garbage not found — skipping")
        return 0
    n = 0
    for split, out_split in (("train", "train"), ("valid", "val")):
        img_dir, lbl_dir = base / split / "images", base / split / "labels"
        if not img_dir.exists():
            continue
        for img in img_dir.glob("*.jpg"):
            lbl = lbl_dir / (img.stem + ".txt")
            if not lbl.exists():
                continue
            stem = f"gd_{split}_{img.stem}"
            out_lbl = V3 / "labels" / out_split / (stem + ".txt")
            if not out_lbl.exists():
                out_lbl.write_text(_remap_label(lbl, {}) if False else
                                   _remap_all_to(lbl, C_GARBAGE))
            _link(img, V3 / "images" / out_split / (stem + ".jpg"))
            n += 1
    print(f"[v3] garbage: +{n} images -> garbage_dump")
    return n


def _remap_all_to(lbl: Path, target: int) -> str:
    lines = []
    for l in lbl.read_text().splitlines():
        parts = l.split()
        if len(parts) == 5:
            lines.append(" ".join([str(target)] + parts[1:]))
    return "\n".join(lines) + ("\n" if lines else "")


def add_crack_neg():
    base = KAGGLE / "crack_neg"
    n = 0
    for img in (base / "Negative").glob("*.jpg"):
        stem = f"cn_neg_{img.stem}"
        (V3 / "labels" / "train" / (stem + ".txt")).touch()
        _link(img, V3 / "images" / "train" / (stem + ".jpg"))
        n += 1
    for img in (base / "Positive").glob("*.jpg"):
        stem = f"cn_pos_{img.stem}"
        lbl = V3 / "labels" / "train" / (stem + ".txt")
        if not lbl.exists():
            lbl.write_text(f"{C_CRACK} 0.5 0.5 1.0 1.0\n")
        _link(img, V3 / "images" / "train" / (stem + ".jpg"))
        n += 1
    print(f"[v3] crack_neg: +{n} images (6,000 negatives + 1,500 crack patches)")
    return n


def add_taco():
    base = KAGGLE / "taco"
    img_root = lbl_root = None
    for cand in [base / "train", base]:
        if (cand / "images").exists():
            img_root, lbl_root = cand / "images", cand / "labels"
            break
    if img_root is None:
        print("[v3] TACO not found — skipping")
        return 0
    n = 0
    for img in img_root.glob("*.jpg"):
        lbl = lbl_root / (img.stem + ".txt")
        if not lbl.exists():
            continue
        stem = f"taco_{img.stem}"
        out_lbl = V3 / "labels" / "train" / (stem + ".txt")
        if not out_lbl.exists():
            out_lbl.write_text(_remap_all_to(lbl, C_GARBAGE))
        _link(img, V3 / "images" / "train" / (stem + ".jpg"))
        n += 1
    print(f"[v3] TACO: +{n} images -> garbage_dump")
    return n


def add_all():
    """Returns dict of per-source counts for reporting."""
    return {
        "roaddamage": add_roaddamage(),
        "garbage": add_garbage(),
        "crack_neg": add_crack_neg(),
        "taco": add_taco(),
    }


if __name__ == "__main__":
    V3.mkdir(exist_ok=True)
    for split in ("train", "val"):
        (V3 / "images" / split).mkdir(parents=True, exist_ok=True)
        (V3 / "labels" / split).mkdir(parents=True, exist_ok=True)
    add_all()
