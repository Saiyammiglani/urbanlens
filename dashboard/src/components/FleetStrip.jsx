import React, { useEffect, useState } from "react";
import { fetchFleet } from "../lib/api.js";

const TYPE_ICONS = {
  bus: "🚌", garbage_truck: "🚛", ambulance: "🚑", tanker: "🚒",
  municipal_car: "🚗", police_car: "🚓", other: "🔧",
};
const TYPE_LABELS = {
  bus: "Bus", garbage_truck: "Garbage truck", ambulance: "Ambulance",
  tanker: "Water tanker", municipal_car: "Municipal car", police_car: "Police car",
  other: "Fleet vehicle",
};

function since(ts) {
  const s = Math.max(0, (Date.now() - new Date(ts.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(ts) ? ts : ts + "Z").getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function FleetStrip() {
  const [fleet, setFleet] = useState([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try { const r = await fetchFleet(); if (alive) setFleet(r.fleet || []); } catch {}
    };
    load();
    const id = setInterval(load, 8000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!fleet.length) return null;
  const active = fleet.filter((v) => v.last_seen && Date.now() - new Date(v.last_seen.endsWith("Z") ? v.last_seen : v.last_seen + "Z").getTime() < 5 * 60 * 1000);

  return (
    <div className="fleet-strip">
      <div className="panel-title-row">
        <div className="panel-title">
          Reporting fleet <span className="sidebar-count">{fleet.length}</span>
        </div>
        <span className="fleet-active">{active.length} active now</span>
      </div>
      <div className="fleet-scroll">
        {fleet.map((v) => (
          <div key={v.code} className={`fleet-chip ${active.some((a) => a.code === v.code) ? "active" : ""}`}
               title={`${TYPE_LABELS[v.vehicle_type] || "Vehicle"} · last seen ${since(v.last_seen)}`}>
            <span className="fleet-chip-icon">{TYPE_ICONS[v.vehicle_type] || "🔧"}</span>
            <span className="fleet-chip-code">{v.code}</span>
            <span className="fleet-chip-seen">{since(v.last_seen)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
