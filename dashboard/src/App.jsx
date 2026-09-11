import React, { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, Marker, ZoomControl, useMap } from "react-leaflet";
import L from "leaflet";
import { fetchIncidents, fetchStats, fetchZones, transition } from "./lib/api.js";
import { TILE_URL, TILE_ATTRIBUTION, TILE_MAX_ZOOM } from "./lib/tiles.js";
import { realtimeAvailable, subscribeRealtime } from "./lib/realtime.js";
import {
  LABEL_META,
  labelColor,
  labelIcon,
  prettyLabel,
  severityRadius,
} from "./lib/labels.js";
import IncidentFeed from "./components/IncidentFeed.jsx";
import IncidentDetail from "./components/IncidentDetail.jsx";
import EvidenceImage from "./components/EvidenceImage.jsx";
import SmartRoute from "./components/SmartRoute.jsx";
import StatsBar from "./components/StatsBar.jsx";
import Uploads from "./components/Uploads.jsx";
import LiveCam from "./components/LiveCam.jsx";
import TrafficView from "./components/TrafficView.jsx";
import FleetPanel from "./components/FleetPanel.jsx";

const STATUSES = ["new", "confirmed", "assigned", "in_progress", "resolved", "rejected"];

const CITIES = {
  Delhi: [28.6139, 77.209],
  Mumbai: [19.0850, 72.8730],
  Bengaluru: [12.9550, 77.6150],
};

/* ---------- view rail definition ---------- */

const VIEWS = [
  { id: "overview",  label: "Live Map"  },
  { id: "incidents", label: "Incidents" },
  { id: "traffic",   label: "Traffic"   },
  { id: "analytics", label: "Analytics" },
  { id: "uploads",   label: "Media"     },
  { id: "livecam",   label: "Live Cam"  },
];

const RAIL_ICONS = {
  overview: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
    </svg>
  ),
  incidents: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 6h13M8 12h13M8 18h13" />
      <circle cx="3.5" cy="6" r="1" fill="currentColor" />
      <circle cx="3.5" cy="12" r="1" fill="currentColor" />
      <circle cx="3.5" cy="18" r="1" fill="currentColor" />
    </svg>
  ),
  traffic: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 17h3l2-4 3 2 3-6 3 3h2" />
      <circle cx="6" cy="6" r="1.4" />
      <circle cx="12" cy="4.5" r="1.4" />
      <circle cx="18" cy="7" r="1.4" />
    </svg>
  ),
  analytics: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" />
      <path d="M7 15l4-5 3 3 5-7" />
    </svg>
  ),
  uploads: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2" />
    </svg>
  ),
  livecam: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="M16 10l6-3v10l-6-3" />
    </svg>
  ),
};

/* ---------- small helpers ---------- */

function MapRef() {
  const map = useMap();
  useEffect(() => { window.__map = map; }, [map]);
  return null;
}

function CityView({ center }) {
  const map = useMap();
  useEffect(() => {
    if (center) map.setView(center, 13);
  }, [center?.[0], center?.[1]]);
  return null;
}

function pingIcon(color) {
  return L.divIcon({
    className: "ping-wrapper",
    html: `<span class="ping-ring" style="--ping:${color}"></span>`,
    iconSize: [0, 0],
  });
}

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="topbar-clock">
      {now.toLocaleTimeString("en-IN", { hour12: false })}
    </span>
  );
}

function UpdatedAgo({ lastSync }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (!lastSync) return null;
  const s = Math.max(0, Math.round((Date.now() - lastSync) / 1000));
  return <span className="updated-ago">updated {s}s ago</span>;
}

/* ============================================================
   APP
   ============================================================ */

export default function App() {
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState(null);
  const [zones, setZones] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [labelFilter, setLabelFilter] = useState("");
  const [minSeverity, setMinSeverity] = useState(1);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [routeMode, setRouteMode] = useState(false);
  const [city, setCity] = useState("Delhi");
  const [hovered, setHovered] = useState(null);
  const [toast, setToast] = useState(null);
  const [view, setView] = useState("overview");
  const [lastSync, setLastSync] = useState(null);
  const prevIds = useRef(new Set());
  const dataSig = useRef("");
  const lastPingSig = useRef(null);
  const [pingIds, setPingIds] = useState(new Set());
  const firstLoad = useRef(true);

  const refresh = async () => {
    const sig = `${statusFilter}|${labelFilter}|${minSeverity}`;
    try {
      const [incs, st, zs] = await Promise.all([
        fetchIncidents({
          status: statusFilter || undefined,
          label: labelFilter || undefined,
          min_severity: minSeverity,
          limit: 1000,
        }),
        fetchStats(),
        fetchZones(),
      ]);
      setIncidents(incs);
      setStats(st);
      setZones(zs);
      dataSig.current = sig;
      setError(null);
      setLastSync(Date.now());
    } catch (e) {
      setError(e.message);
    } finally {
      if (firstLoad.current) firstLoad.current = false;
    }
  };

  const loading = firstLoad.current && !stats && !error;

  const showToast = (message, tone = "error") => {
    setToast({ message, tone });
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => {
    refresh();
    // fallback poll only — Supabase Realtime triggers refresh instantly on
    // new rows, so this just backstops dropped websockets (and keeps shared-
    // pooler egress low: list responses no longer carry base64 evidence)
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [statusFilter, labelFilter, minSeverity]);

  // Supabase Realtime: instant refresh on new rows (free tier).
  // Falls back silently to the 4 s poll above if env vars are unset.
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useEffect(() => {
    if (!realtimeAvailable()) return;
    let pending = null;
    const unsub = subscribeRealtime(
      ["incidents", "observations", "traffic_alerts", "traffic_segments"],
      () => {
        if (pending) return; // debounce bursts from one bus
        pending = setTimeout(() => { pending = null; refreshRef.current(); }, 400);
      }
    );
    return () => { clearTimeout(pending); unsub(); };
  }, []);

  useEffect(() => {
    if (selected) {
      const cur = incidents.find((i) => i.id === selected.id);
      if (cur && cur.updated_at !== selected.updated_at) setSelected(cur);
    }
  }, [incidents]);

  useEffect(() => {
    const ids = new Set(incidents.map((i) => i.id));
    const fresh = [...ids].filter((id) => !prevIds.current.has(id));
    const sigChanged = lastPingSig.current !== dataSig.current;
    lastPingSig.current = dataSig.current;
    prevIds.current = ids;
    if (!sigChanged && fresh.length && prevIds.current.size > fresh.length) {
      setPingIds((p) => new Set([...p, ...fresh]));
      const t = setTimeout(() => {
        setPingIds((p) => {
          const n = new Set(p);
          fresh.forEach((f) => n.delete(f));
          return n;
        });
      }, 8000);
      return () => clearTimeout(t);
    }
  }, [incidents]);

  const labels = useMemo(
    () =>
      [...new Set([...Object.keys(LABEL_META), ...incidents.map((i) => i.label)])].sort(),
    [incidents]
  );

  const act = async (incident, status) => {
    try {
      await transition(incident.id, status, "control-room", "");
      refresh();
    } catch (e) {
      showToast(`Couldn't update incident: ${e.message}`);
    }
  };

  /* ---------- shared map layers ---------- */

  const mapLayers = (
    <>
      <TileLayer
        attribution={TILE_ATTRIBUTION}
        url={TILE_URL}
        maxZoom={TILE_MAX_ZOOM}
      />
      <ZoomControl position="bottomright" />
      {incidents.map((inc) => {
        const c = labelColor(inc.label);
        const closed = inc.status === "resolved" || inc.status === "rejected";
        const hot = hovered === inc.id || selected?.id === inc.id;
        return (
          <CircleMarker
            key={inc.id}
            center={[inc.lat, inc.lon]}
            radius={severityRadius(inc.severity) + (hot ? 2 : 0)}
            pathOptions={{
              interactive: !routeMode,
              color: c,
              weight: hot ? 4 : closed ? 1.5 : 2.5,
              fillColor: inc.status === "rejected" ? "#0b0c0f" : c,
              fillOpacity: inc.status === "resolved" ? 0.15 : inc.status === "rejected" ? 0.05 : hot ? 0.85 : 0.6,
              dashArray: closed ? "4 3" : null,
            }}
            eventHandlers={{ click: () => setSelected(inc) }}
          >
            <Tooltip>
              <b style={{ color: c }}>{prettyLabel(inc.label)}</b> · sev {inc.severity} · {prettyLabel(inc.status)}
              {inc.address ? <><br />📍 {inc.address}</> : null}
            </Tooltip>
            <Popup>
              <b style={{ color: c }}>{labelIcon(inc.label)} {prettyLabel(inc.label)}</b>
              <br />severity {inc.severity}/10 · confidence {(inc.confidence * 100).toFixed(0)}%
              <br />status: {prettyLabel(inc.status)}
              <br />seen {inc.observation_count}× · {inc.assigned_dept || "unassigned"}
              {(inc.has_image || inc.image_b64) && (
                <>
                  <br />
                  <EvidenceImage id={inc.id} hasImage width="200" />
                </>
              )}
            </Popup>
          </CircleMarker>
        );
      })}
      {incidents
        .filter((inc) => pingIds.has(inc.id))
        .map((inc) => (
          <Marker
            key={`ping-${inc.id}`}
            position={[inc.lat, inc.lon]}
            icon={pingIcon(labelColor(inc.label))}
            interactive={false}
          />
        ))}
      <CityView center={CITIES[city]} />
      <MapRef />
      <SmartRoute zones={zones} active={routeMode} onActiveChange={setRouteMode} />
    </>
  );

  /* ---------- filter toolbar ---------- */

  const toolbar = (
    <div className="toolbar">
      <select className="select" value={city} onChange={(e) => setCity(e.target.value)} title="Switch city view">
        {Object.keys(CITIES).map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
      <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} title="Filter by status">
        <option value="">All statuses</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>{prettyLabel(s)}</option>
        ))}
      </select>
      <select className="select" value={labelFilter} onChange={(e) => setLabelFilter(e.target.value)} title="Filter by issue type">
        <option value="">All issue types</option>
        {labels.map((l) => (
          <option key={l} value={l}>{prettyLabel(l)}</option>
        ))}
      </select>
      <select className="select" value={minSeverity} onChange={(e) => setMinSeverity(Number(e.target.value))} title="Filter by severity">
        <option value={1}>Any severity</option>
        <option value={4}>Severity ≥ 4</option>
        <option value={6}>Severity ≥ 6</option>
        <option value={8}>Critical only (≥ 8)</option>
      </select>
      <span className="result-count" aria-live="polite">
        {incidents.length} shown
      </span>
    </div>
  );

  /* ---------- legend ---------- */

  const legend = (
    <div className="legend">
      <div className="legend-title">Issue Types</div>
      {labels.map((l) => (
        <div key={l} className="legend-row">
          <span className="legend-dot" style={{ background: labelColor(l) }} />
          {prettyLabel(l)}
        </div>
      ))}
      <div className="legend-divider" />
      <div className="legend-title">Status</div>
      <div className="legend-row"><span className="legend-dot" style={{ background: "#475569" }} /> Open / active</div>
      <div className="legend-row"><span className="legend-dot" style={{ background: "transparent", border: "1.5px dashed #64748b" }} /> Resolved</div>
      <div className="legend-row"><span className="legend-dot" style={{ background: "transparent", border: "1.5px solid #64748b" }} /> Rejected</div>
      <div className="legend-divider" />
      <div className="legend-title">Dot Size</div>
      <div className="legend-row">Larger = higher severity</div>
    </div>
  );

  /* ---------- analytics ---------- */

  const STATUS_COLORS = {
    new: "#22d3ee", confirmed: "#60a5fa", assigned: "#a78bfa",
    in_progress: "#fbbf24", resolved: "#34d399", rejected: "#6b7280",
  };

  const analytics = stats ? (
    <div className="analytics-grid">
      <div className="an-card">
        <div className="an-card-title">Status Pipeline</div>
        {STATUSES.map((s) => {
          const n = incidents.filter((i) => i.status === s).length;
          const max = Math.max(1, ...STATUSES.map((st) => incidents.filter((i) => i.status === st).length));
          return (
            <div className="an-row" key={s}>
              <span className="an-name">{prettyLabel(s)}</span>
              <div className="an-track">
                <div className="an-fill" style={{ width: `${(n / max) * 100}%`, background: STATUS_COLORS[s] }} />
              </div>
              <span className="an-count" style={{ color: STATUS_COLORS[s] }}>{n}</span>
            </div>
          );
        })}
      </div>
      <div className="an-card">
        <div className="an-card-title">Issue Mix</div>
        {Object.entries(stats.by_label).sort((a, b) => b[1] - a[1]).map(([l, n]) => (
          <div className="an-row" key={l}>
            <span className="an-name">{labelIcon(l)} {prettyLabel(l)}</span>
            <div className="an-track">
              <div className="an-fill" style={{ width: `${(n / Math.max(...Object.values(stats.by_label))) * 100}%`, background: labelColor(l) }} />
            </div>
            <span className="an-count">{n}</span>
          </div>
        ))}
      </div>
      <div className="an-card">
        <div className="an-card-title">Recent Detections</div>
        <div className="an-list">
          {[...incidents]
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
            .slice(0, 6)
            .map((i) => (
              <div className="an-item" key={i.id}>
                <span
                  className="legend-dot"
                  style={{
                    background: labelColor(i.label),
                    borderRadius: "50%",
                    width: 10, height: 10, flexShrink: 0,
                    boxShadow: `0 0 6px ${labelColor(i.label)}`,
                  }}
                />
                <b style={{ fontSize: 12, flex: 1 }}>{prettyLabel(i.label)}</b>
                <span className="meta-item">sev {i.severity}/10</span>
                <span className="meta-item">{Math.round(i.confidence * 100)}%</span>
                <span className="meta-item">{i.assigned_dept || "unassigned"}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  ) : null;

  /* ---------- page title helper ---------- */

  const PAGE_TITLES = {
    overview:  { title: "Urban Intelligence",    sub: <>AI-powered city monitoring · <b>{city}</b> · {incidents.length} incidents on map</> },
    incidents: { title: "Incident Queue",        sub: <>Full queue · {incidents.length} shown · sorted by severity</> },
    traffic:   { title: "Traffic Intelligence",  sub: <>Vehicle density · congestion heat · bottlenecks · ANPR &amp; pedestrian safety</> },
    analytics: { title: "Analytics",             sub: <>Live breakdown of the current filter set</> },
    uploads:   { title: "Media Upload",          sub: <>Drop route footage — the fleet agent processes it end-to-end</> },
    livecam:   { title: "Live Camera",           sub: <>Real-time detection from a live camera · auto-reports to the map</> },
  };

  const isFixedView = view === "overview" || view === "traffic";

  /* ============================================================
     RENDER
     ============================================================ */

  return (
    <div className="app">
      {/* ===== Topbar ===== */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">U</div>
          <div className="brand-text">
            <div className="brand-name">UrbanLens</div>
            <div className="brand-sub">Mobile Urban Intelligence · BEL</div>
          </div>
        </div>

        <div className="topbar-center">
          <div className={`live-pill ${error ? "offline" : ""}`}>
            <span className="live-dot" />
            {error ? "Backend Offline" : "Live"}
            {!error && lastSync && (
              <>
                <span className="live-sep" aria-hidden="true">·</span>
                <UpdatedAgo lastSync={lastSync} />
              </>
            )}
          </div>
        </div>

        <div className="topbar-right">
          <Clock />
        </div>
      </header>

      {/* ===== Body: rail + main ===== */}
      <div className="app-body">
        <nav className="rail" aria-label="Views">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              className={`rail-btn ${view === v.id ? "active" : ""}`}
              onClick={() => setView(v.id)}
              aria-label={v.label}
              aria-pressed={view === v.id}
            >
              {RAIL_ICONS[v.id]}
              <span className="rail-tip">{v.label}</span>
            </button>
          ))}
          <div className="rail-spacer" />
        </nav>

        <main className={`main ${isFixedView ? "fixed-view" : "scrollable-view"}`}>
          <div className="main-inner">
            {/* ===== Page header ===== */}
            <div className="pagehead">
              <div>
                <h1 className="pagehead-title">{PAGE_TITLES[view]?.title}</h1>
                <div className="pagehead-sub">{PAGE_TITLES[view]?.sub}</div>
              </div>
              <div className="pagehead-actions">
                <button className="btn" onClick={refresh} title="Refresh data">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                    <path d="M3 3v5h5" />
                  </svg>
                  Refresh
                </button>
              </div>
            </div>

            {/* ===== Metric band — hidden on traffic (has its own overlay stats) ===== */}
            {view !== "traffic" && <StatsBar stats={stats} />}

            {/* ===== Error banner ===== */}
            {error && (
              <div className="error-banner" role="alert">
                <span className="error-banner-icon">⚠</span>
                <div className="error-banner-body">
                  <b>Can't reach the UrbanLens backend</b>
                  <span>Live fleet updates are paused. Retrying automatically every 4 s.</span>
                </div>
                <button className="btn" onClick={refresh}>Retry now</button>
              </div>
            )}

            {/* ===== VIEWS ===== */}

            {view === "overview" && (
              <div className="workspace overview-workspace">

                {/* ── Left: Fleet Panel ── */}
                <FleetPanel />

                {/* ── Center: Map ── */}
                <div className="map-card">
                  <div className="map-head">
                    <div className="map-head-left">
                      <span className="map-head-title">
                        Live Monitoring · <span className="map-head-city">{city}</span>
                      </span>
                    </div>
                    <span className="map-head-dotcount">
                      ● {incidents.length} on map
                    </span>
                  </div>
                  <div className="map-body">
                    <MapContainer center={[28.6139, 77.209]} zoom={12} minZoom={4} maxZoom={19} scrollWheelZoom zoomControl={false}>
                      {mapLayers}
                    </MapContainer>
                    {toolbar}
                    {legend}
                    {incidents.length === 0 && !error && !loading && (
                      <div className="map-empty">
                        <div className="map-empty-card">
                          <div className="icon">🛰️</div>
                          Waiting for fleet detections…
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* ── Right: Incident Queue + Evidence Panel ── */}
                <div className="right-column">
                  {selected ? (
                    <IncidentDetail
                      incident={selected}
                      onClose={() => setSelected(null)}
                      onAct={act}
                    />
                  ) : (
                    <IncidentFeed
                      incidents={incidents}
                      loading={loading}
                      selected={selected}
                      onSelect={(inc) => setSelected(selected?.id === inc.id ? null : inc)}
                      onAct={act}
                      onHover={setHovered}
                    />
                  )}
                </div>
              </div>
            )}

            {view === "incidents" && (
              <IncidentFeed
                incidents={incidents}
                loading={loading}
                selected={selected}
                onSelect={(inc) => setSelected(selected?.id === inc.id ? null : inc)}
                onAct={act}
                onHover={setHovered}
                variant="full"
              />
            )}

            {view === "analytics" && analytics}

            {view === "traffic" && <TrafficView city={city} />}

            {view === "uploads" && <Uploads onToast={showToast} />}

            {view === "livecam" && <LiveCam onToast={showToast} />}
          </div>
        </main>
      </div>

      {/* ===== Toast ===== */}
      {toast && (
        <div className={`toast toast-${toast.tone}`} role="status">
          <span>{toast.tone === "error" ? "⚠ " : "✓ "}{toast.message}</span>
          <button className="toast-close" onClick={() => setToast(null)} aria-label="Dismiss">✕</button>
        </div>
      )}
    </div>
  );
}
