import React, { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMap } from "react-leaflet";
import { fetchIncidents, fetchStats, fetchZones, transition } from "./lib/api.js";
import {
  LABEL_META,
  labelColor,
  labelIcon,
  prettyLabel,
  severityRadius,
} from "./lib/labels.js";
import IncidentFeed from "./components/IncidentFeed.jsx";
import IncidentDetail from "./components/IncidentDetail.jsx";
import SmartRoute from "./components/SmartRoute.jsx";
import StatsBar from "./components/StatsBar.jsx";

const STATUSES = ["new", "confirmed", "assigned", "in_progress", "resolved", "rejected"];

const CITIES = {
  Delhi: [28.6139, 77.209],
  Mumbai: [19.0850, 72.8730],
  Bengaluru: [12.9550, 77.6150],
};

/** Recenter the map when the selected city changes. */
function CityView({ center }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, 13);
  }, [center[0], center[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/** Expose map instance for tests/debug (window.__map). */
function MapRef() {
  const map = useMap();
  useEffect(() => { window.__map = map; }, [map]);
  return null;
}

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

  const refresh = async () => {
    try {
      const [incs, st, zs] = await Promise.all([
        fetchIncidents({
          status: statusFilter || undefined,
          label: labelFilter || undefined,
          min_severity: minSeverity,
        }),
        fetchStats(),
        fetchZones(),
      ]);
      setIncidents(incs);
      setStats(st);
      setZones(zs);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [statusFilter, labelFilter, minSeverity]);

  // keep selected card fresh
  useEffect(() => {
    if (selected) {
      const cur = incidents.find((i) => i.id === selected.id);
      if (cur && cur.updated_at !== selected.updated_at) setSelected(cur);
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
      alert(e.message);
    }
  };

  return (
    <div className="app">
      {/* ===== Header ===== */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">🚌</div>
          <div>
            <div className="brand-name">UrbanLens</div>
            <div className="brand-sub">Mobile Urban Intelligence · BEL · SIH26124</div>
          </div>
        </div>

        <div className="topbar-right">
          <div className={`live-indicator ${error ? "offline" : ""}`}>
            <span className="live-dot" />
            {error ? "Backend Offline" : "Live · auto-refresh 4s"}
          </div>
          {stats && (
            <div className="topbar-right" style={{ gap: 14 }}>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1 }}>{stats.total}</div>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Incidents
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1, color: "#f59e0b" }}>{stats.open}</div>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Open
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1, color: "#22c55e" }}>{stats.resolved}</div>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Resolved
                </div>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* ===== KPI strip ===== */}
      <StatsBar stats={stats} />

      {/* ===== Toolbar ===== */}
      <div className="toolbar">
        <select className="select" value={city} onChange={(e) => setCity(e.target.value)} title="Switch city view">
          {Object.keys(CITIES).map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <span className="toolbar-label">Filters</span>
        <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{prettyLabel(s)}</option>
          ))}
        </select>
        <select className="select" value={labelFilter} onChange={(e) => setLabelFilter(e.target.value)}>
          <option value="">All issue types</option>
          {labels.map((l) => (
            <option key={l} value={l}>{prettyLabel(l)}</option>
          ))}
        </select>
        <select className="select" value={minSeverity} onChange={(e) => setMinSeverity(Number(e.target.value))}>
          <option value={1}>Any severity</option>
          <option value={4}>Severity ≥ 4</option>
          <option value={6}>Severity ≥ 6</option>
          <option value={8}>Critical only (≥ 8)</option>
        </select>

        <div className="toolbar-spacer" />
        <span className="result-count">
          {incidents.length} shown{labelFilter ? ` · ${prettyLabel(labelFilter)}` : ""}
        </span>
        <button className="btn" onClick={refresh}>⟳ Refresh</button>
      </div>

      {/* ===== Main ===== */}
      <main className="layout">
        <div className="map-pane">
          <MapContainer center={[28.6139, 77.209]} zoom={12} scrollWheelZoom>
            <TileLayer
              attribution='&copy; OpenStreetMap contributors &copy; Esri, HERE, Garmin'
              url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
            />
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
            />
            {incidents.map((inc) => {
              const c = labelColor(inc.label);
              const closed = inc.status === "resolved" || inc.status === "rejected";
              return (
                <CircleMarker
                  key={inc.id}
                  center={[inc.lat, inc.lon]}
                  radius={severityRadius(inc.severity)}
                  pathOptions={{
                    interactive: !routeMode, // click-through while planning a route
                    color: c,
                    weight: closed ? 1.5 : 2.5,
                    fillColor: inc.status === "rejected" ? "#0b1120" : c,
                    fillOpacity: inc.status === "resolved" ? 0.15 : inc.status === "rejected" ? 0.05 : 0.6,
                    dashArray: closed ? "4 3" : null,
                  }}
                  eventHandlers={{ click: () => setSelected(inc) }}
                >
                  <Tooltip>
                    <b style={{ color: c }}>{prettyLabel(inc.label)}</b> · sev {inc.severity} · {prettyLabel(inc.status)}
                  </Tooltip>
                  <Popup>
                    <b style={{ color: c }}>{labelIcon(inc.label)} {prettyLabel(inc.label)}</b>
                    <br />severity {inc.severity}/10 · confidence {(inc.confidence * 100).toFixed(0)}%
                    <br />status: {prettyLabel(inc.status)}
                    <br />seen {inc.observation_count}× · {inc.assigned_dept || "unassigned"}
                    {inc.image_b64 && (
                      <>
                        <br />
                        <img src={`data:image/jpeg;base64,${inc.image_b64}`} width="200" style={{ borderRadius: 6, marginTop: 6 }} alt="evidence" />
                      </>
                    )}
                  </Popup>
                </CircleMarker>
              );
            })}
            <CityView center={CITIES[city]} />
            <MapRef />
            <SmartRoute zones={zones} active={routeMode} onActiveChange={setRouteMode} />
          </MapContainer>

          {incidents.length === 0 && !error && (
            <div className="map-empty">
              <div className="map-empty-card">
                <div className="icon">🛰️</div>
                Waiting for fleet detections…
              </div>
            </div>
          )}

          {/* Legend */}
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

          {/* Detail drawer */}
          <IncidentDetail
            incident={selected}
            onClose={() => setSelected(null)}
            onAct={act}
          />
        </div>

        <IncidentFeed
          incidents={incidents}
          selected={selected}
          onSelect={(inc) => setSelected(selected?.id === inc.id ? null : inc)}
          onAct={act}
        />
      </main>
    </div>
  );
}
