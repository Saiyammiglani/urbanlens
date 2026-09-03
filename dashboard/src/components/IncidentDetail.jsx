import React, { useEffect, useState } from "react";
import {
  labelColor,
  labelIcon,
  prettyLabel,
  sevClass,
  statusClass,
  timeAgo,
} from "../lib/labels.js";

const WORKFLOW = [
  { status: "confirmed", label: "Confirm", desc: "Validate the detection" },
  { status: "assigned", label: "Assign", desc: "Route to department" },
  { status: "in_progress", label: "Start Work", desc: "Crew is on site" },
  { status: "resolved", label: "Mark Resolved", desc: "Issue fixed & verified" },
];
const EXTRA_ACTIONS = [
  { status: "rejected", label: "Reject", desc: "False positive / invalid" },
  { status: "in_progress", label: "Reopen", desc: "Issue recurred", only: "resolved" },
];

// legal transitions (mirrors backend ALLOWED map)
const ALLOWED = {
  new: ["confirmed", "rejected"],
  confirmed: ["assigned", "rejected"],
  assigned: ["in_progress", "rejected"],
  in_progress: ["resolved", "rejected"],
  resolved: ["in_progress"],
  rejected: ["confirmed"],
};

function sevColor(sev) {
  return sev >= 8 ? "#f87171" : sev >= 5 ? "#fbbf24" : "#34d399";
}

export default function IncidentDetail({ incident, onClose, onAct }) {
  // reverse-geocoded address from the backend (Nominatim), fetched on open.
  // Hooks must run before any conditional return (rules of hooks).
  const [address, setAddress] = useState(incident?.address || null);
  useEffect(() => {
    if (!incident) return;
    let alive = true;
    setAddress(incident.address || null);
    if (!incident.address) {
      fetch(`${import.meta.env.DEV ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000")}/api/v1/incidents/${incident.id}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (alive && d?.address) setAddress(d.address); })
        .catch(() => {});
    }
    return () => { alive = false; };
  }, [incident?.id, incident?.address]);

  if (!incident) return null;

  const c = labelColor(incident.label);

  return (
    <div className="detail-drawer">
      <button className="detail-close" onClick={onClose} title="Close">✕</button>

      <div className="detail-kicker">
        {incident.assigned_dept || "Unassigned"} · ID {incident.id.slice(0, 8)}
      </div>
      <h2 className="detail-title">
        {labelIcon(incident.label)} {prettyLabel(incident.label)}
      </h2>
      <div className="detail-sub">
        {address ? (
          <>
            <span className="detail-address" title={address}>📍 {address}</span>
            <span className="detail-coords">{incident.lat.toFixed(5)}, {incident.lon.toFixed(5)}</span>
          </>
        ) : (
          <span>{incident.lat.toFixed(5)}, {incident.lon.toFixed(5)}</span>
        )}
      </div>

      {incident.image_b64 && (
        <img
          className="detail-evidence"
          src={`data:image/jpeg;base64,${incident.image_b64}`}
          alt="Evidence capture (privacy-filtered)"
        />
      )}

      {/* severity meter — real value visualized */}
      <div className="detail-sev">
        <div className="detail-sev-label">
          <span>Severity</span>
          <span>{incident.severity} / 10</span>
        </div>
        <div className="detail-sev-track">
          <div
            className="detail-sev-fill"
            style={{ width: `${incident.severity * 10}%`, background: sevColor(incident.severity) }}
          />
        </div>
      </div>

      <div className="detail-grid">
        <div className="detail-cell">
          <div className="detail-cell-label">Confidence</div>
          <div className="detail-cell-value">{Math.round(incident.confidence * 100)}%</div>
        </div>
        <div className="detail-cell">
          <div className="detail-cell-label">Sightings</div>
          <div className="detail-cell-value">{incident.observation_count}×</div>
        </div>
        <div className="detail-cell">
          <div className="detail-cell-label">First Seen</div>
          <div className="detail-cell-value">{timeAgo(incident.created_at)}</div>
        </div>
        <div className="detail-cell">
          <div className="detail-cell-label">Status</div>
          <div className="detail-cell-value">
            <span className={`status-badge ${statusClass(incident.status)}`}>
              {prettyLabel(incident.status)}
            </span>
          </div>
        </div>
      </div>

      <div className="detail-actions">
        {[...WORKFLOW, ...EXTRA_ACTIONS]
          .filter((a) => !a.only || incident.status === a.only)
          .map((a) => {
            const legal = (ALLOWED[incident.status] || []).includes(a.status);
            return (
              <button
                key={a.label}
                className="btn"
                onClick={() => legal && onAct(incident, a.status)}
                disabled={!legal}
                title={legal ? a.desc : `Not allowed from "${prettyLabel(incident.status)}"`}
                style={a.label === "Reject" && legal ? { color: "#f87171" } : undefined}
              >
                {a.label}
              </button>
            );
          })}
      </div>
    </div>
  );
}
