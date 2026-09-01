const BASE = import.meta.env.DEV ? "/api/v1" : (import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1");

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
