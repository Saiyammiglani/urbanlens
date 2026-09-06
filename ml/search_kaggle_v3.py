"""Search Kaggle for real-world datasets for all 9 UrbanLens classes.
Writes results to a JSON report. Also flags datasets likely to contain
background/negative images (essential to reduce false positives).
"""
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

TOKEN = ""
with open(os.path.join(os.path.dirname(__file__), "..", ".env")) as f:
    for line in f:
        if line.startswith("KAGGLE_API_TOKEN="):
            TOKEN = line.strip().split("=", 1)[1]

QUERIES = {
    "pothole": ["pothole detection", "pothole segmentation", "road pothole"],
    "crack": ["road crack detection", "concrete crack", "pavement crack dataset"],
    "garbage_dump": ["garbage detection yolo", "litter trash detection", "waste detection"],
    "waterlogging": ["flood street detection", "urban flood", "waterlogged road"],
    "open_manhole": ["manhole detection", "open manhole"],
    "broken_streetlight": ["street light detection", "streetlight pole", "lamp post detection"],
    "roadside_debris": ["road debris detection", "roadside garbage", "debris detection"],
    "faded_signage": ["traffic sign detection", "road sign recognition", "sign damage"],
    "illegal_parking": ["parking violation", "car detection street", "vehicle parking"],
}


def search(q):
    url = f"https://www.kaggle.com/api/v1/datasets/list?search={urllib.parse.quote(q)}&maxSize=2000000000"
    req = urllib.request.Request(url, headers={})
    import base64
    auth = base64.b64encode(f"{TOKEN}:".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


import urllib.parse

report = {}
for cls, queries in QUERIES.items():
    report[cls] = []
    seen = set()
    for q in queries:
        try:
            results = search(q)
        except Exception as e:
            print(f"  ! search failed: {q} ({e})", file=sys.stderr)
            continue
        for r in results[:10]:
            ref = r.get("ref") or r.get("refNullable")
            if not ref or ref in seen:
                continue
            seen.add(ref)
            report[cls].append({
                "ref": ref,
                "title": r.get("title") or r.get("titleNullable") or "",
                "size_mb": round((r.get("totalBytes") or r.get("totalBytesNullable") or 0) / 1e6, 1),
                "usability": r.get("usabilityRating") or 0,
                "subtitle": (r.get("subtitle") or r.get("subtitleNullable") or "")[:110],
            })
    print(f"{cls}: {len(report[cls])} candidates")

with open(os.path.join(os.path.dirname(__file__), "kaggle_search_report.json"), "w") as f:
    json.dump(report, f, indent=1)
print("\nreport -> ml/kaggle_search_report.json")
