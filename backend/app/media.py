"""Media upload: dashboard can drop recorded MP4s; backend stores them under
edge/media/uploads and can launch the edge agent on them (one-click replay).
"""
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .config import settings

router = APIRouter(prefix="/api/v1/media", tags=["media"])

ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT / "edge" / "media" / "uploads"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv"}

# filename -> {"proc": Popen, "vehicle": str, "route": str, "started": str}
RUNNING: dict[str, dict] = {}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(415, f"unsupported file type — allowed: {sorted(ALLOWED_EXT)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (max 500 MB)")
    dest = MEDIA_DIR / f"{uuid.uuid4().hex[:8]}_{name}"
    dest.write_bytes(data)
    return {
        "filename": dest.name,
        "size_mb": round(len(data) / 1e6, 1),
    }


class ProcessIn(BaseModel):
    vehicle: str = "MH01BV4521"
    vehicle_type: str = "bus"
    route: str = "routes/route_02.json"
    lat: float | None = None   # device location of the uploader — route is
    lon: float | None = None   # translated to start at these real coords


@router.post("/{filename}/process")
def process(filename: str, payload: ProcessIn):
    filename = Path(filename).name          # block path traversal (../)
    video = MEDIA_DIR / filename
    if not video.exists():
        raise HTTPException(404, "upload not found")
    if filename in RUNNING and RUNNING[filename]["proc"].poll() is None:
        raise HTTPException(409, "agent already running on this file")

    edge_dir = ROOT / "edge"
    cmd = [
        settings.EDGE_PYTHON, "main.py",
        "--vehicle", payload.vehicle,
        "--type", payload.vehicle_type,
        "--route", payload.route,
        "--video", str(video),
    ]
    if payload.lat is not None and payload.lon is not None:
        cmd += ["--gps-origin", f"{payload.lat:.6f},{payload.lon:.6f}"]
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    log = (MEDIA_DIR / f"{video.stem}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd, cwd=str(edge_dir), stdout=log, stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    RUNNING[filename] = {
        "proc": proc,
        "vehicle": payload.vehicle,
        "vehicle_type": payload.vehicle_type,
        "route": payload.route,
        "started": datetime.now(timezone.utc).isoformat(),
    }
    return {"filename": filename, "pid": proc.pid, "vehicle": payload.vehicle}


@router.get("")
def list_media():
    items = []
    for f in sorted(MEDIA_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix.lower() not in ALLOWED_EXT:
            continue
        run = RUNNING.get(f.name)
        state = "idle"
        if run:
            state = "running" if run["proc"].poll() is None else "done"
        items.append({
            "filename": f.name,
            "size_mb": round(f.stat().st_size / 1e6, 1),
            "status": state,
            **({"vehicle": run["vehicle"]} if run else {}),
        })
    return {"uploads": items}
