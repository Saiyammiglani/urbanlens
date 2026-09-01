"""Build the v2 dataset: 9 classes.

Combines the v1 dataset (pothole, crack, garbage_dump) with new Roboflow-sourced
classes (waterlogging, open_manhole, broken_streetlight, roadside_debris,
faded_signage, illegal_parking).

Output: ml/dataset_v2/  (images/{train,val}, labels/{train,val}) + dataset_v2.yaml
"""
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path

ML = Path(__file__).resolve().parent
DL = ML / "datasets" / "downloads"
OUT = ML / "dataset_v2"

CLASSES = [
    "pothole", "crack", "garbage_dump", "waterlogging", "open_manhole",
    "broken_streetlight", "roadside_debris", "faded_signage", "illegal_parking",
]
NAME_TO_ID = {n: i for i, n in enumerate(CLASSES)}

# source zip -> {source_class_id: target_class_name or None(skip)}
SOURCES = [
    ("waterlogging.zip", {0: "waterlogging"}),
    ("v2_open_manhole.zip", {0: None, 1: "open_manhole", 2: "pothole"}),
    ("v2_street_light.zip", {0: "broken_streetlight"}),
    ("v2_road_hazards.zip", {0: "crack", 1: None, 2: "roadside_debris", 3: "pothole"}),
    ("v2_damaged_signs.zip", {0: "faded_signage", 1: None, 2: None}),
    ("v2_illegal_parking.zip", {0: None, 1: "illegal_parking", 2: None, 3: None}),
    # v3 export merges Poor-Damaged + Poor-Old into single "Poor" class
    ("v2_hazard_signs.zip", {0: None, 1: None, 2: None, 3: None, 4: "faded_signage"}),
    ("v2_debris_small.zip", {0: "roadside_debris"}),
    # boost sources
    ("v2_floods_agroudy.zip", {0: "waterlogging", 1: "waterlogging", 2: "waterlogging"}),
    ("v2_illegal_parking2.zip", {0: "illegal_parking"}),
    # obstacles + worksite_materials on road
    ("v2_road_obstacles.zip", {0: None, 1: None, 2: "roadside_debris", 3: None, 4: None, 5: "roadside_debris"}),
    # loose street litter
    ("v2_litter_fxyqc.zip", {0: "roadside_debris"}),
]

VAL_FRACTION = 0.1
random.seed(42)

IMG_EXT = (".jpg", ".jpeg", ".png")


def build():
    if OUT.exists():
        print("[!] dataset_v2 exists — remove it to rebuild"); return
    for split in ("train", "val"):
        (OUT / "images" / split).mkdir(parents=True)
        (OUT / "labels" / split).mkdir(parents=True)

    stats = Counter()
    box_stats = Counter()

    # 1) copy v1 dataset (classes 0-2 unchanged)
    v1 = ML / "dataset"
    n = 0
    for split in ("train", "val"):
        for img in (v1 / "images" / split).iterdir():
            if img.suffix.lower() not in IMG_EXT:
                continue
            lbl = v1 / "labels" / split / (img.stem + ".txt")
            shutil.copy2(img, OUT / "images" / split / img.name)
            if lbl.exists():
                shutil.copy2(lbl, OUT / "labels" / split / lbl.name)
                for line in lbl.read_text().splitlines():
                    if line.strip():
                        box_stats[CLASSES[int(line.split()[0])]] += 1
            stats["v1_" + split] += 1
            n += 1
    print(f"[v1] copied {n} images (labels unchanged)")

    # 2) extract + remap new sources
    tmp = ML / "datasets" / "_v2_tmp"
    for zip_name, class_map in SOURCES:
        zp = DL / zip_name
        if not zp.exists():
            print(f"[!] missing {zip_name}, skipping"); continue
        if tmp.exists():
            shutil.rmtree(tmp)
        with zipfile.ZipFile(zp) as z:
            z.extractall(tmp)

        src_name = zip_name.replace(".zip", "")
        # index images across splits
        imgs = [p for p in tmp.rglob("*") if p.suffix.lower() in IMG_EXT]
        kept = dropped = 0
        random.shuffle(imgs)
        val_count = int(len(imgs) * VAL_FRACTION)

        for i, img in enumerate(imgs):
            split = "val" if i < val_count else "train"
            lbl = img.parent.parent / "labels" / (img.stem + ".txt")
            if not lbl.exists():
                lbl = img.with_suffix(".txt")
            if not lbl.exists():
                dropped += 1
                continue
            out_lines = []
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                try:
                    cid = int(float(parts[0]))
                except ValueError:
                    continue
                target = class_map.get(cid)
                if target is None:
                    continue
                out_lines.append(f"{NAME_TO_ID[target]} " + " ".join(parts[1:5]))
                box_stats[target] += 1
            if not out_lines:
                dropped += 1
                continue  # no relevant boxes -> skip image
            new_stem = f"{src_name}_{img.stem}"[:200]
            shutil.copy2(img, OUT / "images" / split / img.name if False else OUT / "images" / split / (new_stem + img.suffix.lower()))
            (OUT / "labels" / split / (new_stem + ".txt")).write_text("\n".join(out_lines) + "\n")
            stats[src_name + "_" + split] += 1
            kept += 1
        print(f"[{src_name}] kept {kept}, dropped {dropped} (no relevant boxes)")

    if tmp.exists():
        shutil.rmtree(tmp)

    # 3) yaml
    (ML / "dataset_v2.yaml").write_text(
        f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/val\n\n"
        f"nc: {len(CLASSES)}\nnames: {CLASSES}\n"
    )
    print("\n=== dataset_v2 summary ===")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    print("  total train:", sum(v for k, v in stats.items() if k.endswith('_train')))
    print("  total val:", sum(v for k, v in stats.items() if k.endswith('_val')))
    print("\nboxes per class:")
    for c in CLASSES:
        print(f"  {c:20s} {box_stats[c]}")
    print("\nwrote", ML / "dataset_v2.yaml")


if __name__ == "__main__":
    build()
