import React, { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, Tooltip, ZoomControl, useMap } from "react-leaflet";
import { BASE } from "../lib/api.js";
import { TILE_URL, TILE_ATTRIBUTION, TILE_MAX_ZOOM } from "../lib/tiles.js";

const CITIES = {
  Delhi: [28.6139, 77.2295],
  Mumbai: [19.05, 72.86],
  Bengaluru: [12.955, 77.615],
};

const KIND_META = {
  anpr: { icon: "🚔", label: "ANPR · plate captured", color: "#e05252" },
  rash_driving: { icon: "⚡", label: "Rash driving", color: "#e08a3c" },
  school_zone: { icon: "🎒", label: "Vulnerable pedestrians", color: "#4c9be8" },
  pedestrian: { icon: "🚸", label: "Pedestrian risk", color: "#4c9be8" },
};

function congColor(c) {
  if (c >= 75) return "#e05252";
  if (c >= 50) return "#e0a03c";
  if (c >= 25) return "#d8d84a";
  return "#4cd464";
}

function MapRecenter({ center }) {
  const map = useMap();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    map.flyTo(center, 13, { duration: 0.8 });
  }, [center[0], center[1]]); // eslint-disable-line
  return null;
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export default function TrafficView({ city }) {
  const [segments, setSegments] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [od, setOd] = useState(null);
  const [delays, setDelays] = useState(null);
  const [hour, setHour] = useState(null); // null = all day
  const [showOD, setShowOD] = useState(true);
  const [err, setErr] = useState(null);
  const [selAlert, setSelAlert] = useState(null);

  useEffect(() => {
    let alive = true;
    setErr(null);
    Promise.all([
      get(`/traffic/segments?city=${city}&limit=600`),
      get(`/traffic/bottlenecks?city=${city}`),
      get(`/traffic/alerts?city=${city}&limit=30`),
      get(`/traffic/od?city=${city}`),
      get(`/traffic/delays?city=${city}`),
    ]).then(([s, b, a, o, d]) => {
      if (!alive) return;
      setSegments(s); setBottlenecks(b); setAlerts(a); setOd(o); setDelays(d);
    }).catch((e) => alive && setErr(String(e)));
    return () => { alive = false; };
  }, [city]);

  // recompute display when hour filter changes (client-side slice)
  const shown = useMemo(
    () => (hour === null ? segments : segments.filter((s) => s.hour === hour)),
    [segments, hour]
  );

  const maxFlow = od?.flows?.[0]?.volume || 1;
  const avgCong = shown.length
    ? (shown.reduce((a, s) => a + s.congestion, 0) / shown.length).toFixed(0)
    : 0;
  const totalVeh = shown.reduce((a, s) => a + s.total_vehicles, 0);

  return (
    <div className="traffic-view" data-testid="traffic-view">
      {/* left: map */}
      <div className="traffic-map-wrap">
        <MapContainer center={CITIES[city]} zoom={12} className="traffic-map" zoomControl={false}>
          <TileLayer
            attribution={TILE_ATTRIBUTION}
            url={TILE_URL}
            maxZoom={TILE_MAX_ZOOM}
          />
          <ZoomControl position="bottomright" />
          <MapRecenter center={CITIES[city]} />

          {/* congestion heat circles */}
          {shown.map((s) => (
            <CircleMarker
              key={s.id}
              center={[s.lat, s.lon]}
              radius={6 + (s.congestion / 100) * 16}
              pathOptions={{
                color: congColor(s.congestion), weight: 1,
                fillColor: congColor(s.congestion), fillOpacity: 0.55,
              }}
            >
              <Tooltip>
                <b>congestion {s.congestion}/100</b> · {s.route}
                <br />{s.total_vehicles} vehicles · {s.speed_kmh} km/h · {s.hour}:00
                {s.persons ? <><br />🚶 {s.persons} pedestrians</> : null}
              </Tooltip>
            </CircleMarker>
          ))}

          {/* OD flow lines */}
          {showOD && od?.flows?.map((f, i) => (
            <Polyline
              key={`od-${i}`}
              positions={[[f.from_lat, f.from_lon], [f.to_lat, f.to_lon]]}
              pathOptions={{
                color: "#7ec8f0", weight: 1 + (f.volume / maxFlow) * 3,
                opacity: 0.35, dashArray: "6 8",
              }}
              interactive={false}
            />
          ))}

          {/* alert pins */}
          {alerts.map((a) => {
            const m = KIND_META[a.kind] || KIND_META.anpr;
            const hot = selAlert?.id === a.id;
            return (
              <CircleMarker
                key={a.id}
                center={[a.lat, a.lon]}
                radius={hot ? 10 : 7}
                pathOptions={{ color: m.color, weight: hot ? 3 : 2, fillColor: m.color, fillOpacity: 0.9 }}
                eventHandlers={{ click: () => setSelAlert(hot ? null : a) }}
              >
                <Tooltip>
                  <b style={{ color: m.color }}>{m.icon} {m.label}</b>
                  {a.plate ? <><br />🔢 {a.plate} ({(a.plate_confidence * 100).toFixed(0)}%)</> : null}
                  <br />{a.city}
                </Tooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>

        {/* map overlay stats */}
        <div className="traffic-overlay">
          <div className="traffic-chip">
            <span className="traffic-chip-num">{avgCong}</span>
            <span className="traffic-chip-lab">avg congestion</span>
          </div>
          <div className="traffic-chip">
            <span className="traffic-chip-num">{totalVeh}</span>
            <span className="traffic-chip-lab">vehicles counted</span>
          </div>
          <div className="traffic-chip">
            <span className="traffic-chip-num">{alerts.length}</span>
            <span className="traffic-chip-lab">safety alerts</span>
          </div>
          <div className="traffic-legend">
            <div><span className="dot" style={{ background: congColor(85) }} /> jammed 75+</div>
            <div><span className="dot" style={{ background: congColor(60) }} /> heavy 50-74</div>
            <div><span className="dot" style={{ background: congColor(35) }} /> moderate 25-49</div>
            <div><span className="dot" style={{ background: congColor(10) }} /> free</div>
          </div>
        </div>
        {err && <div className="traffic-error">⚠ {err}</div>}
      </div>

      {/* right: panels */}
      <div className="traffic-side">
        <div className="traffic-controls">
          <select className="select" value={hour ?? ""} onChange={(e) => setHour(e.target.value === "" ? null : Number(e.target.value))} title="Filter by hour">
            <option value="">All day</option>
            {[7, 8, 9, 12, 17, 18, 19, 20].map((h) => <option key={h} value={h}>{h}:00</option>)}
          </select>
          <button className={`btn btn-sm ${showOD ? "btn-on" : ""}`} onClick={() => setShowOD(!showOD)} title="Toggle origin-destination flows">
            ⇄ OD flows
          </button>
        </div>

        {/* bottlenecks */}
        <div className="traffic-panel">
          <h3 className="traffic-h">⛔ Bottleneck corridors</h3>
          <table className="traffic-table" data-testid="bottleneck-list">
            <thead><tr><th>Route</th><th>Cong.</th><th>Speed</th><th>Veh.</th></tr></thead>
            <tbody>
              {bottlenecks.map((b) => (
                <tr key={b.route}>
                  <td>{b.route.split("·")[1] || b.route}</td>
                  <td><span className="cong-pill" style={{ background: congColor(b.avg_congestion) }}>{b.avg_congestion}</span></td>
                  <td>{b.avg_speed_kmh} km/h</td>
                  <td>{b.vehicles_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* alerts */}
        <div className="traffic-panel traffic-alerts" data-testid="traffic-alerts">
          <h3 className="traffic-h">🚨 Safety alerts <span className="count-badge">{alerts.length}</span></h3>
          <div className="alert-list">
            {alerts.map((a) => {
              const m = KIND_META[a.kind] || KIND_META.anpr;
              const active = selAlert?.id === a.id;
              return (
                <button key={a.id} className={`alert-card ${active ? "active" : ""}`} onClick={() => setSelAlert(active ? null : a)}>
                  <div className="alert-head">
                    <span className="alert-kind" style={{ color: m.color }}>{m.icon} {m.label}</span>
                    <span className="alert-time">{new Date(a.detected_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  </div>
                  {a.plate && (
                    <div className="alert-plate">
                      <span className="plate-text">{a.plate}</span>
                      <span className="plate-conf">{(a.plate_confidence * 100).toFixed(0)}% conf</span>
                    </div>
                  )}
                  <div className="alert-notes">{a.notes}</div>
                  <div className="alert-meta">📍 {a.city} · {a.vehicle_type || "pedestrians"} · GPS locked</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* route delays */}
        <div className="traffic-panel">
          <h3 className="traffic-h">⏱ Route delays (vs free-flow)</h3>
          {delays?.routes?.map((r) => {
            const worst = Math.max(...r.hours.map((h) => h.delay_pct));
            const peak = r.hours.find((h) => h.delay_pct === worst);
            const bars = r.hours.map((h) => (
              <div key={h.hour} className="delay-col" title={`${h.hour}:00 · ${h.delay_pct}% delay · ${h.avg_speed_kmh} km/h`}>
                <div className="delay-bar" style={{ height: `${Math.max(3, h.delay_pct)}%`, background: congColor(h.congestion) }} />
                <span className="delay-hr">{h.hour}</span>
              </div>
            ));
            return (
              <div key={r.route} className="delay-route">
                <div className="delay-title">{r.route.split("·")[1] || r.route} <span className="delay-worst">peak +{worst}% @ {peak?.hour}:00</span></div>
                <div className="delay-chart">{bars}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
