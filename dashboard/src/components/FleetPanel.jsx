import React, { useEffect, useState } from "react";
import { fetchFleet } from "../lib/api.js";

const TYPE_ICONS = {
  bus: "🚌", garbage_truck: "🚛", ambulance: "🚑", tanker: "🚒",
  municipal_car: "🚗", police_car: "🚓", other: "🔧",
};
const TYPE_LABELS = {
  bus: "Bus", garbage_truck: "Garbage Truck", ambulance: "Ambulance",
  tanker: "Water Tanker", municipal_car: "Municipal Car", police_car: "Police Car",
  other: "Fleet Vehicle",
};
const TYPE_COLORS = {
  bus: "#60a5fa", garbage_truck: "#34d399", ambulance: "#f87171",
  tanker: "#38bdf8", municipal_car: "#a78bfa", police_car: "#fbbf24", other: "#94a3b8",
};

function since(ts) {
  const s = Math.max(0, (Date.now() - new Date(ts.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(ts) ? ts : ts + "Z").getTime()) / 1000);
  if (s < 60) return { label: "now", seconds: s };
  if (s < 3600) return { label: `${Math.floor(s / 60)}m ago`, seconds: s };
  if (s < 86400) return { label: `${Math.floor(s / 3600)}h ago`, seconds: s };
  return { label: `${Math.floor(s / 86400)}d ago`, seconds: s };
}

function isActive(v) {
  if (!v.last_seen) return false;
  const ts = v.last_seen.endsWith("Z") ? v.last_seen : v.last_seen + "Z";
  return Date.now() - new Date(ts).getTime() < 5 * 60 * 1000;
}

export default function FleetPanel() {
  const [fleet, setFleet] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [, tick] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetchFleet();
        if (alive) setFleet(r.fleet || []);
      } catch {}
    };
    load();
    const loadId = setInterval(load, 8000);
    // tick every 15s to refresh "last seen" labels
    const tickId = setInterval(() => tick((t) => t + 1), 15000);
    return () => { alive = false; clearInterval(loadId); clearInterval(tickId); };
  }, []);

  const active = fleet.filter(isActive);
  const inactive = fleet.filter((v) => !isActive(v));

  if (!fleet.length) return (
    <div className="fleet-panel">
      <div className="fleet-panel-head">
        <span className="fleet-panel-title">Active Fleet</span>
        <span className="fleet-panel-count">0</span>
      </div>
      <div className="fleet-panel-empty">
        <div className="fleet-empty-icon">🚌</div>
        <div className="fleet-empty-text">No vehicles reporting</div>
        <div className="fleet-empty-sub">Fleet chips appear when buses transmit GPS</div>
      </div>
    </div>
  );

  return (
    <div className="fleet-panel">
      {/* Header */}
      <div className="fleet-panel-head">
        <span className="fleet-panel-title">Active Fleet</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="fleet-panel-active-pill">
            <span className="fleet-live-dot" />
            {active.length} live
          </span>
          <span className="fleet-panel-count">{fleet.length}</span>
        </div>
      </div>

      <div className="fleet-panel-body">
        {/* Active vehicles */}
        {active.length > 0 && (
          <div className="fleet-section">
            <div className="fleet-section-label">
              <span className="fleet-section-dot active" />
              Online · {active.length}
            </div>
            {active.map((v) => {
              const { label: sinceLabel } = since(v.last_seen);
              const color = TYPE_COLORS[v.vehicle_type] || "#94a3b8";
              const open = expanded === v.code;
              return (
                <button
                  key={v.code}
                  className={`fleet-card active${open ? " open" : ""}`}
                  onClick={() => setExpanded(open ? null : v.code)}
                >
                  <div className="fleet-card-row">
                    <div className="fleet-card-icon" style={{ background: `${color}18`, border: `1px solid ${color}30` }}>
                      <span>{TYPE_ICONS[v.vehicle_type] || "🔧"}</span>
                    </div>
                    <div className="fleet-card-body">
                      <div className="fleet-card-code">{v.code}</div>
                      <div className="fleet-card-type">{TYPE_LABELS[v.vehicle_type] || "Vehicle"}</div>
                    </div>
                    <div className="fleet-card-right">
                      <div className="fleet-card-ping" style={{ background: color }} />
                      <div className="fleet-card-seen" style={{ color }}>{sinceLabel}</div>
                    </div>
                  </div>
                  {open && (
                    <div className="fleet-card-detail">
                      <div className="fleet-detail-row">
                        <span className="fleet-detail-key">Type</span>
                        <span className="fleet-detail-val">{TYPE_LABELS[v.vehicle_type] || "Unknown"}</span>
                      </div>
                      <div className="fleet-detail-row">
                        <span className="fleet-detail-key">Last GPS</span>
                        <span className="fleet-detail-val">{sinceLabel}</span>
                      </div>
                      {v.lat && v.lon && (
                        <div className="fleet-detail-row">
                          <span className="fleet-detail-key">Position</span>
                          <span className="fleet-detail-val mono">{v.lat?.toFixed(4)}, {v.lon?.toFixed(4)}</span>
                        </div>
                      )}
                      {v.speed != null && (
                        <div className="fleet-detail-row">
                          <span className="fleet-detail-key">Speed</span>
                          <span className="fleet-detail-val">{Math.round(v.speed)} km/h</span>
                        </div>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Inactive vehicles */}
        {inactive.length > 0 && (
          <div className="fleet-section">
            <div className="fleet-section-label">
              <span className="fleet-section-dot" />
              Offline · {inactive.length}
            </div>
            {inactive.map((v) => {
              const { label: sinceLabel } = since(v.last_seen);
              return (
                <div key={v.code} className="fleet-card inactive">
                  <div className="fleet-card-row">
                    <div className="fleet-card-icon dim">
                      <span>{TYPE_ICONS[v.vehicle_type] || "🔧"}</span>
                    </div>
                    <div className="fleet-card-body">
                      <div className="fleet-card-code dim">{v.code}</div>
                      <div className="fleet-card-type">{TYPE_LABELS[v.vehicle_type] || "Vehicle"}</div>
                    </div>
                    <div className="fleet-card-right">
                      <div className="fleet-card-seen">{sinceLabel}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
