"""Fetch v2 datasets from Roboflow Universe via API (downloads YOLOv8 exports)."""
import json
import time
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path

API_KEY = "38iQ4n96WvfQBf58nmdm"
OUT = Path(__file__).resolve().parent / "datasets" / "downloads"
OUT.mkdir(parents=True, exist_ok=True)

DATASETS = [
    # (project slug, name for zip)
    ("qassim-university-rgdar/open-manhole-image-dataset1", "open_manhole"),
    ("sashank-s/street-light", "street_light"),
    ("street-hazard-wquul/road-hazards", "road_hazards"),
    ("concave/faded-or-damaged-signs-detection", "damaged_signs"),
    ("chung-yi-lai/carpark-and-license-plate-with-illegal-parking", "illegal_parking"),
]


def api(path):
    url = f"https://api.roboflow.com/{path}?api_key={API_KEY}&format=json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def download(url, dest):
    with urllib.request.urlopen(url, timeout=600) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


for slug, name in DATASETS:
    zdest = OUT / f"v2_{name}.zip"
    if zdest.exists():
        print(f"[skip] {name} already downloaded")
        continue
    try:
        # find latest version
        info = api(slug)
        versions = info.get("versions", [])
        if not versions:
            print(f"[FAIL] {slug}: no versions")
            continue
        latest = max(v["id"].rsplit("/", 1)[-1] for v in versions if "/" in v.get("id", ""))
        ver_slug = f"{slug}/{latest}"

        print(f"[{name}] {slug} v{latest} ...", flush=True)
        export = api(f"{ver_slug}/yolov8")
        link = (export.get("export") or {}).get("link")
        if not link:
            print(f"  no export link: {json.dumps(export)[:200]}")
            continue
        download(link, zdest)
        size = zdest.stat().st_size / 1e6
        with zipfile.ZipFile(zdest) as z:
            names = z.namelist()
        imgs = len([n for n in names if n.endswith((".jpg", ".png", ".jpeg"))])
        print(f"  downloaded {size:.1f} MB, {imgs} images")
    except Exception as e:
        print(f"  ERROR: {e}")
    time.sleep(2)
