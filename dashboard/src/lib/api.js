export const BASE = import.meta.env.DEV ? "/api/v1" : (import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1");

export async function fetchIncidents(params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
  ).toString();
  const res = await fetch(`${BASE}/incidents${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`incidents: ${res.status}`);
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${BASE}/incidents/stats`);
  if (!res.ok) throw new Error(`stats: ${res.status}`);
  return res.json();
}

export async function transition(incidentId, status, author = "admin", note = "", assigned_dept = null) {
  const res = await fetch(`${BASE}/incidents/${incidentId}/transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, author, note, assigned_dept }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `transition failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchZones() {
  try {
    const res = await fetch(`${BASE}/routing/zones`);
    if (res.ok) return (await res.json()).zones || [];
  } catch {}
  return [];
}

/* ---------- media uploads ---------- */

export async function uploadMedia(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/media/upload`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `upload failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchMedia() {
  const res = await fetch(`${BASE}/media`);
  if (!res.ok) throw new Error(`media: ${res.status}`);
  return (await res.json()).uploads || [];
}

export async function processMedia(filename, vehicle, route, lat = null, lon = null, vehicleType = "bus") {
  const body = { vehicle, route, vehicle_type: vehicleType };
  if (lat != null && lon != null) { body.lat = lat; body.lon = lon; }
  const res = await fetch(`${BASE}/media/${filename}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `process failed: ${res.status}`);
  }
  return res.json();
}

/* ---------- live camera ---------- */

export async function liveStart(cam = 0, vehicle = "MH01BV4521", vehicleType = "bus") {
  const res = await fetch(`${BASE}/live/start?cam=${cam}&vehicle=${encodeURIComponent(vehicle)}&vehicle_type=${encodeURIComponent(vehicleType)}`, { method: "POST" });
  return res.json();
}

export async function liveStop() {
  const res = await fetch(`${BASE}/live/stop`, { method: "POST" });
  return res.json();
}

export async function liveReport(enabled) {
  const res = await fetch(`${BASE}/live/report?enabled=${enabled}`, { method: "POST" });
  return res.json();
}

export async function liveStatus() {
  const res = await fetch(`${BASE}/live/status`);
  return res.json();
}

export async function fetchFleet() {
  const res = await fetch(`${BASE}/incidents/fleet`);
  if (!res.ok) return { fleet: [] };
  return res.json();
}

export async function pushDeviceGps(lat, lon, speedKmh = 0, heading = 0) {
  const res = await fetch(`${BASE}/live/gps`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon, speed_kmh: speedKmh, heading }),
  });
  return res.json();
}
