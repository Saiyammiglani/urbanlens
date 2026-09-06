import React, { useEffect, useRef, useState } from "react";
import { uploadMedia, fetchMedia, processMedia } from "../lib/api.js";

const ROUTES = [
  { id: "routes/route_02.json", label: "Delhi · Route 02" },
  { id: "routes/route_mumbai.json", label: "Mumbai · Route 01" },
  { id: "routes/route_bengaluru.json", label: "Bengaluru · Route 01" },
  { id: "routes/route_01.json", label: "Delhi · Route 01" },
];

export const VEHICLE_TYPES = [
  { id: "bus", label: "🚌 Bus", plate: "MH01BV4521" },
  { id: "garbage_truck", label: "🚛 Garbage truck", plate: "MH01G5678" },
  { id: "ambulance", label: "🚑 Ambulance", plate: "MH01A1086" },
  { id: "tanker", label: "🚒 Water tanker", plate: "DL1PD1234" },
  { id: "municipal_car", label: "🚗 Municipal car", plate: "KA01M2947" },
  { id: "police_car", label: "🚓 Police car", plate: "DL01P0821" },
  { id: "other", label: "🔧 Other fleet vehicle", plate: "GA01O0000" },
];

export default function Uploads({ onToast }) {
  const [uploads, setUploads] = useState([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(null); // filename being processed
  const [progress, setProgress] = useState(null); // {name, pct}
  const [route, setRoute] = useState(ROUTES[0].id);
  const [vehicle, setVehicle] = useState(VEHICLE_TYPES[0].plate);
  const [vehicleType, setVehicleType] = useState(VEHICLE_TYPES[0].id);
  const inputRef = useRef(null);

  const refresh = async () => {
    try { setUploads(await fetchMedia()); } catch {}
  };
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  const handleFiles = async (files) => {
    for (const file of files) {
      if (!/\.(mp4|mov|avi|mkv)$/i.test(file.name)) {
        onToast?.(`${file.name}: not a video file`, "error");
        continue;
      }
      setProgress({ name: file.name, pct: 0 });
      // XHR for real upload progress
      await new Promise((resolve) => {
        const fd = new FormData();
        fd.append("file", file);
        const xhr = new XMLHttpRequest();
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) setProgress({ name: file.name, pct: Math.round((e.loaded / e.total) * 100) });
        };
        xhr.onload = () => {
          const ok = xhr.status === 200;
          onToast?.(ok ? `${file.name} uploaded` : `${file.name}: upload failed`, ok ? "ok" : "error");
          resolve();
        };
        xhr.onerror = () => { onToast?.(`${file.name}: upload failed`, "error"); resolve(); };
        const BASE = import.meta.env.DEV ? "/api/v1" : (import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1");
        xhr.open("POST", `${BASE}/media/upload`);
        xhr.send(fd);
      });
      setProgress(null);
    }
    refresh();
  };

  const process = async (filename) => {
    setBusy(filename);
    try {
      // attach the uploader's real device location — the simulated route is
      // translated to start at these coordinates
      let lat = null, lon = null;
      if (navigator.geolocation) {
        const pos = await new Promise((resolve) => {
          navigator.geolocation.getCurrentPosition(resolve, () => resolve(null),
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 });
        });
        if (pos) { lat = pos.coords.latitude; lon = pos.coords.longitude; }
      }
      await processMedia(filename, vehicle, route, lat, lon, vehicleType);
      onToast?.(
        lat != null
          ? `Agent launched on ${filename} at your device location (${lat.toFixed(4)}, ${lon.toFixed(4)})`
          : `Agent launched on ${filename} — detections will appear on the Live Map`,
        "ok",
      );
    } catch (e) {
      onToast?.(e.message, "error");
    } finally {
      setBusy(null);
      refresh();
    }
  };

  return (
    <div className="upload-page">
      {/* dropzone */}
      <div
        className={`dropzone ${drag ? "drag" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFiles([...e.dataTransfer.files]); }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
      >
        <div className="dropzone-icon">🎬</div>
        <div className="dropzone-title">Drop route videos here</div>
        <div className="dropzone-sub">MP4 · MOV · AVI · MKV — up to 500 MB · or click to browse</div>
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
          multiple
          hidden
          onChange={(e) => { handleFiles([...e.target.files]); e.target.value = ""; }}
        />
      </div>

      {progress && (
        <div className="upload-progress">
          <span>Uploading {progress.name}… {progress.pct}%</span>
          <div className="mix-track"><div className="mix-fill" style={{ width: `${progress.pct}%`, background: "#22d3ee" }} /></div>
        </div>
      )}

      {/* processing options */}
      <div className="upload-options">
        <label className="upload-field">
          <span>Fleet vehicle type</span>
          <select
            className="select"
            value={vehicleType}
            onChange={(e) => {
              setVehicleType(e.target.value);
              const t = VEHICLE_TYPES.find((t) => t.id === e.target.value);
              if (t) setVehicle(t.plate); // adopt a realistic plate for that type
            }}
          >
            {VEHICLE_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </label>
        <label className="upload-field">
          <span>Vehicle plate / code</span>
          <input className="plate-input" value={vehicle} onChange={(e) => setVehicle(e.target.value)} placeholder="e.g. MH01BV4521" />
        </label>
        <label className="upload-field">
          <span>Simulated GPS route</span>
          <select className="select" value={route} onChange={(e) => setRoute(e.target.value)}>
            {ROUTES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </label>
      </div>

      {/* uploads list */}
      <div className="upload-list">
        <div className="panel-title">Uploaded footage <span className="sidebar-count">{uploads.length}</span></div>
        {uploads.length === 0 && (
          <div className="empty">
            <div className="icon">📼</div>
            <h3>No uploads yet</h3>
            <p>Drop a dashcam video above — the fleet agent will process it with the trained model.</p>
          </div>
        )}
        {uploads.map((u) => (
          <div key={u.filename} className="card upload-card">
            <div className="card-top">
              <span className="sev-badge low">{u.size_mb} MB</span>
              <span className="card-time">{
                u.status === "running" ? `running on ${u.vehicle || "agent"}` :
                u.status === "done" ? "processed" : "ready to process"
              }</span>
            </div>
            <div className="card-title">📼 {u.filename}</div>
            <div className="card-meta">
              <span className={`status-badge ${u.status === "running" ? "status-assigned" : u.status === "done" ? "status-resolved" : "status-new"}`}>
                {u.status === "running" ? "processing" : u.status === "done" ? "processed" : "ready"}
              </span>
              <div className="card-actions" onClick={(e) => e.stopPropagation()}>
                <button disabled={u.status === "running" || busy === u.filename} onClick={() => process(u.filename)}>
                  {u.status === "running" ? "Processing…" : busy === u.filename ? "Launching…" : "▶ Process with model"}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
