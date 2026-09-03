import React, { useEffect, useRef, useState } from "react";
import { liveStart, liveStop, liveReport, liveStatus, pushDeviceGps } from "../lib/api.js";
import { VEHICLE_TYPES } from "./Uploads.jsx";

export default function LiveCam({ onToast }) {
  const [status, setStatus] = useState(null);
  const [starting, setStarting] = useState(false);
  const [showStream, setShowStream] = useState(false);
  const [vehicleType, setVehicleType] = useState(VEHICLE_TYPES[0].id);
  const [vehicle, setVehicle] = useState(VEHICLE_TYPES[0].plate);
  const imgRef = useRef(null);
  const [imgKey, setImgKey] = useState(0); // force <img> remount per session

  const refresh = async () => {
    try { setStatus(await liveStatus()); } catch {}
  };
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 2000);
    return () => clearInterval(id);
  }, []);

  // --- real device GPS: watch browser geolocation, push fixes to backend ---
  const watchId = useRef(null);
  const startDeviceGps = () => {
    if (watchId.current !== null) return;
    if (!navigator.geolocation) { onToast?.("Device GPS unavailable — using simulated route", "error"); return; }
    watchId.current = navigator.geolocation.watchPosition(
      (pos) => {
        const c = pos.coords;
        pushDeviceGps(
          c.latitude, c.longitude,
          (c.speed && c.speed > 0) ? c.speed * 3.6 : 0,
          c.heading || 0,
        ).catch(() => {});
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED)
          onToast?.("Location permission denied — falling back to simulated route GPS", "error");
        else
          onToast?.(`Device GPS unavailable (${err.message}) — using simulated route`, "error");
        stopDeviceGps();
      },
      { enableHighAccuracy: true, maximumAge: 3000, timeout: 15000 },
    );
  };
  const stopDeviceGps = () => {
    if (watchId.current !== null) {
      navigator.geolocation.clearWatch(watchId.current);
      watchId.current = null;
    }
  };
  useEffect(() => () => stopDeviceGps(), []);

  const running = status?.running;

  const start = async () => {
    setStarting(true);
    try {
      const r = await liveStart(0, vehicle, vehicleType);
      if (r.error) {
        onToast?.(`Camera error: ${r.error}`, "error");
      } else {
        setShowStream(true);
        setImgKey((k) => k + 1);
        startDeviceGps();
        onToast?.("Live camera started — detections stream in real time", "ok");
      }
    } catch (e) {
      onToast?.(e.message, "error");
    } finally {
      setStarting(false);
      refresh();
    }
  };

  const stop = async () => {
    await liveStop();
    stopDeviceGps();
    setShowStream(false);
    setStatus((s) => (s ? { ...s, running: false } : s));
    onToast?.("Live camera stopped", "ok");
  };

  const toggleReport = async () => {
    const next = !(status?.report ?? true);
    await liveReport(next);
    refresh();
    onToast?.(next ? "Reporting ON — confirmed detections enter the pipeline" : "Reporting OFF — view only", "ok");
  };

  return (
    <div className="livecam-page">
      {/* stage */}
      <div className="livecam-stage">
        {showStream && running ? (
          <img
            key={imgKey}
            ref={imgRef}
            className="livecam-stream"
            src={`${(import.meta.env.DEV ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000"))}/api/v1/live/stream.mjpg`}
            alt="Live camera with real-time detection"
            onError={() => onToast?.("Stream interrupted — check backend", "error")}
          />
        ) : (
          <div className="livecam-placeholder">
            <div className="dropzone-icon">📷</div>
            <div className="dropzone-title">
              {starting ? "Opening camera…" : running ? "Camera live — start the stream" : "Camera is off"}
            </div>
            <div className="dropzone-sub">
              Real-time YOLOv8 inference · green box = detected · orange box = confirmed &amp; reported
            </div>
          </div>
        )}
      </div>

      {/* controls */}
      <div className="livecam-controls">
        {!running ? (
          <>
            <select
              className="select"
              value={vehicleType}
              onChange={(e) => {
                setVehicleType(e.target.value);
                const t = VEHICLE_TYPES.find((t) => t.id === e.target.value);
                if (t) setVehicle(t.plate);
              }}
            >
              {VEHICLE_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
            <input
              className="search-input"
              value={vehicle}
              onChange={(e) => setVehicle(e.target.value)}
              title="Vehicle plate / fleet code reporting these detections"
            />
            <button className="btn btn-primary" onClick={start} disabled={starting}>
              {starting ? "Starting…" : "● Start live camera"}
            </button>
          </>
        ) : (
          <button className="btn" onClick={stop}>■ Stop camera</button>
        )}
        {running && (
          <button className="btn" onClick={() => { setImgKey((k) => k + 1); setShowStream(true); }}>
            ⟳ Restart stream
          </button>
        )}
        <button
          className={`btn ${status?.report ? "" : "btn-danger-outline"}`}
          onClick={toggleReport}
          disabled={!running}
          title="When ON, confirmed detections are ingested into the incident pipeline and ping the Live Map"
        >
          {status?.report ? "Reporting: ON" : "Reporting: OFF"}
        </button>
        <div className="livecam-stats">
          {status?.fps ? <span className="meta-item">⚙ {status.fps} fps</span> : null}
          {status ? <span className="meta-item">✓ {status.detections} confirmed detections</span> : null}
          {running && (
            <span
              className="meta-item gps-badge"
              title={status.gps_source === "device" ? "Real device location (browser GPS)" : "Simulated route GPS — grant location permission for real coordinates"}
            >
              {status.gps_source === "device"
                ? `📍 device GPS ${status.lat?.toFixed(4)}, ${status.lon?.toFixed(4)}`
                : "📍 simulated route"}
            </span>
          )}
          {status?.error ? <span className="meta-item" style={{ color: "#f87171" }}>⚠ {status.error}</span> : null}
          {running && status?.vehicle ? <span className="meta-item">🚏 {status.vehicle} · {status.vehicle_type || "bus"}</span> : null}
        </div>
      </div>

      <div className="smartroute-hint">
        GPS priority: <b>real device location</b> (browser geolocation — grant permission
        when prompted) when available, otherwise a simulated bus route. Confirmed
        detections (confidence gate + temporal streak) are geo-tagged with those
        coordinates and ping the Live Map in real time. Real buses use their
        onboard GPS unit (serial NMEA) — same pipeline.
      </div>
    </div>
  );
}
