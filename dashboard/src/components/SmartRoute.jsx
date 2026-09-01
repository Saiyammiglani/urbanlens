import React, { useEffect, useState } from "react";
import { Polyline, Marker, Circle, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { labelColor, labelIcon, prettyLabel } from "../lib/labels.js";

const OSRM = "https://router.project-osrm.org/route/v1/driving";
const CORRIDOR_M = 150; // how close to a zone counts as "on the route"

function pointIcon(color, label) {
  return L.divIcon({
    className: "",
    html: `<div style="width:26px;height:26px;border-radius:50%;background:${color};
      border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,.6);display:grid;
      place-items:center;font-size:12px;font-weight:800;color:#0b1120">${label}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

function haversine(a, b) {
  const R = 6371000, p = Math.PI / 180;
  const x =
    Math.sin(((b[0] - a[0]) * p) / 2) ** 2 +
    Math.cos(a[0] * p) * Math.cos(b[0] * p) * Math.sin(((b[1] - a[1]) * p) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

function ClickCapture({ onPick }) {
  useMapEvents({
    click(e) {
      onPick([e.latlng.lat, e.latlng.lng]);
    },
  });
  return null;
}

/** While routing is active: make incident dots/popups click-through so map
 *  clicks always register, even in incident-dense areas. */
function RoutingModeStyles({ active }) {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    if (active) {
      el.classList.add("routing-mode");
      map.closePopup();
    } else {
      el.classList.remove("routing-mode");
    }
  }, [active, map]);
  return null;
}

function FitRoute({ coords }) {
  const map = useMap();
  useEffect(() => {
    if (coords?.length) map.fitBounds(coords, { padding: [60, 60] });
  }, [coords]);
  return null;
}

async function osrm(a, b, via) {
  const pts = [a, ...(via ? [via] : []), b]
    .map((c) => `${c[1]},${c[0]}`)
    .join(";");
  const res = await fetch(`${OSRM}/${pts}?overview=full&geometries=geojson&alternatives=true`);
  if (!res.ok) throw new Error("OSRM unavailable");
  const data = await res.json();
  if (!data.routes?.length) throw new Error("No route found");
  return data.routes.map((r) => ({
    coords: r.geometry.coordinates.map((c) => [c[1], c[0]]),
    distance_km: (r.distance / 1000).toFixed(1),
    duration_min: Math.round(r.duration / 60),
  }));
}

export default function SmartRoute({ zones, active, onActiveChange }) {
  const setActive = onActiveChange;
  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [routes, setRoutes] = useState([]); // [{coords,distance_km,duration_min}]
  const [cleanRoute, setCleanRoute] = useState(null);
  const [impacts, setImpacts] = useState([]);
  const [status, setStatus] = useState("");

  const reset = () => {
    setStart(null); setEnd(null); setRoutes([]); setCleanRoute(null);
    setImpacts([]); setStatus("");
  };

  // corridor analysis: which zones does the route pass through?
  const analyze = (coords, zs) => {
    const hits = [];
    for (const z of zs) {
      const zc = [z.lat, z.lon];
      let best = Infinity;
      // sample route polyline for proximity (cheap: every 5th point)
      for (let i = 0; i < coords.length; i += 3) {
        const d = haversine(coords[i], zc);
        if (d < best) best = d;
      }
      if (best <= CORRIDOR_M + z.radius_m) hits.push({ ...z, distance_m: Math.round(best) });
    }
    return hits.sort((a, b) => b.max_severity - a.max_severity);
  };

  // compute route(s) when both points set
  useEffect(() => {
    if (!start || !end) return;
    let cancelled = false;
    (async () => {
      setStatus("Finding route…");
      try {
        const rs = await osrm(start, end);
        if (cancelled) return;
        setRoutes([rs[0]]);
        const hits = analyze(rs[0].coords, zones);
        setImpacts(hits);
        if (hits.length) {
          setStatus("Route analyzed — hazard zones found");
          // try to route around the worst zone via a perpendicular offset point
          const worst = hits[0];
          const mid = rs[0].coords[Math.floor(rs[0].coords.length / 2)];
          const dx = worst.lon - mid[1], dy = worst.lat - mid[0];
          const len = Math.hypot(dx, dy) || 1;
          const via = [
            worst.lat + (dy / len) * 0.01 + 0.004 * (dy > 0 ? -1 : 1),
            worst.lon + (dx / len) * 0.01 + 0.004 * (dx > 0 ? -1 : 1),
          ];
          const alt = await osrm(start, end, via);
          if (cancelled) return;
          const altHits = analyze(alt[0].coords, zones);
          if (altHits.length < hits.length || Math.max(...altHits.map((h) => h.max_severity), 0) < worst.max_severity) {
            setCleanRoute({ ...alt[0], avoided: hits.length - altHits.length, remaining: altHits.length });
          }
        } else {
          setStatus("Route analyzed — no hazards on corridor ✓");
        }
      } catch (e) {
        setStatus("Routing error: " + e.message);
      }
    })();
    return () => { cancelled = true; };
  }, [start, end]);

  if (!active) {
    return (
      <div className="smartroute-launch">
        <button className="btn btn-primary" onClick={() => { setActive(true); setStatus("Click map to set START point"); }}>
          🧭 Smart Route
        </button>
      </div>
    );
  }

  const worstSev = impacts.length ? impacts[0].max_severity : 0;
  const banner =
    !start ? "Click map to set START point"
    : !end ? "Click map to set DESTINATION point"
    : impacts.length === 0 ? "✓ Clear route — no hazards detected on corridor"
    : `⚠ ${impacts.length} hazard zone${impacts.length > 1 ? "s" : ""} on route (max severity ${worstSev}/10)`;

  return (
    <>
      {start && <Marker position={start} icon={pointIcon("#22c55e", "A")} />}
      {end && <Marker position={end} icon={pointIcon("#ef4444", "B")} />}
      {routes.map((r, i) => (
        <Polyline key={i} positions={r.coords} pathOptions={{
          color: impacts.length ? "#f59e0b" : "#22c55e", weight: 5, opacity: 0.85,
        }} />
      ))}
      {cleanRoute && (
        <Polyline positions={cleanRoute.coords} pathOptions={{
          color: "#22c55e", weight: 5, opacity: 0.9, dashArray: "10 8",
        }} />
      )}
      {impacts.map((z, i) => (
        <Circle key={i} center={[z.lat, z.lon]} radius={z.radius_m + CORRIDOR_M}
          pathOptions={{ color: "#ef4444", weight: 2, fillColor: "#ef4444", fillOpacity: 0.18 }} />
      ))}
      <FitRoute coords={routes[0]?.coords} />

      <div className="smartroute-panel">
        <div className="smartroute-head">
          <b>🧭 Smart Route Advisory</b>
          <button className="smartroute-close" onClick={() => { setActive(false); reset(); }}>✕</button>
        </div>
        <div className={`smartroute-banner ${impacts.length ? "warn" : "ok"}`}>{banner}</div>
        {routes[0] && (
          <div className="smartroute-meta">
            Route: {routes[0].distance_km} km · {routes[0].duration_min} min
            {cleanRoute && (
              <>
                {" | "}
                <span className="smartroute-clean">
                  Cleaner: {cleanRoute.distance_km} km · {cleanRoute.duration_min} min
                  {cleanRoute.remaining === 0 ? " · avoids ALL zones" : ` · avoids ${cleanRoute.avoided} zone(s), ${cleanRoute.remaining} remain`}
                </span>
              </>
            )}
          </div>
        )}
        {impacts.slice(0, 4).map((z, i) => (
          <div key={i} className="smartroute-zone">
            <span className="legend-dot" style={{ background: labelColor(Object.keys(z.labels)[0]) }} />
            <div className="smartroute-zone-body">
              <b>{z.advisory}</b>
              <div className="smartroute-zone-meta">
                {Object.entries(z.labels).map(([l, n]) => `${labelIcon(l)} ${prettyLabel(l)}×${n}`).join(" · ")} · sev {z.max_severity}/10 · {z.distance_m}m off route
              </div>
            </div>
          </div>
        ))}
        {impacts.length > 4 && <div className="smartroute-meta">+{impacts.length - 4} more zones…</div>}
        {status.startsWith("Finding") && <div className="smartroute-meta">{status}</div>}
        <button className="btn smartroute-reset" onClick={reset}>↺ Reset points</button>
        <div className="smartroute-hint">Powered by live fleet detections · zones auto-update as buses report</div>
      </div>

      <RoutingModeStyles active={active} />
      <ClickCapture onPick={(p) => {
        if (!start) { setStart(p); setStatus("Click map to set DESTINATION"); }
        else if (!end) setEnd(p);
      }} />
    </>
  );
}
