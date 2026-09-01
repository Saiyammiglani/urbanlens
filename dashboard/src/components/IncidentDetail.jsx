import React from "react";
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
  { status: "assigned", label: "Assign", desc: `Route to department` },
  { status: "in_progress", label: "Start Work", desc: "Crew is on site" },
  { status: "resolved", label: "Mark Resolved", desc: "Issue fixed & verified" },
];
const EXTRA_ACTIONS = [
  { status: "rejected", label: "Reject", desc: "False positive / invalid" },
  { status: "in_progress", label: "Reopen", desc: "Issue recurred", only: "resolved" },
];

export default function IncidentDetail({ incident, onClose, onAct }) {
  if (!incident) return null;

  const c = labelColor(incident.label);

  const cells = [
    { label: "Severity", value: `${incident.severity} / 10` },
    { label: "Confidence", value: `${Math.round(incident.confidence * 100)}%` },
    { label: "Sightings", value: `${incident.observation_count}×` },
    { label: "First Seen", value: timeAgo(incident.created_at) },
  ];

  return (
    <div className="detail-drawer">
      <button className="detail-close" onClick={onClose} title="Close">✕</button>

      <div className="detail-title" style={{ color: c }}>
        {labelIcon(incident.label)} {prettyLabel(incident.label)}
      </div>
      <div className="detail-sub">
        {incident.lat.toFixed(5)}, {incident.lon.toFixed(5)} · ID {incident.id.slice(0, 8)}
      </div>

      {incident.image_b64 && (
        <img
          className="detail-evidence"
          src={`data:image/jpeg;base64,${incident.image_b64}`}
          alt="Evidence capture (privacy-filtered)"
        />
      )}

      <div className="detail-grid">
        {cells.map((cell) => (
          <div className="detail-cell" key={cell.label}>
            <div className="detail-cell-label">{cell.label}</div>
            <div className="detail-cell-value">{cell.value}</div>
          </div>
        ))}
        <div className="detail-cell" style={{ gridColumn: "1 / -1" }}>
          <div className="detail-cell-label">Status</div>
          <div className="detail-cell-value">
            <span className={`status-badge ${statusClass(incident.status)}`}>
              {prettyLabel(incident.status)}
            </span>
          </div>
        </div>
        <div className="detail-cell" style={{ gridColumn: "1 / -1" }}>
          <div className="detail-cell-label">Assigned Department</div>
          <div className="detail-cell-value">{incident.assigned_dept || "Unassigned"}</div>
        </div>
      </div>

      <div className="detail-actions">
        {WORKFLOW.map((a) => (
          <button
            key={a.status}
            className="btn"
            onClick={() => onAct(incident, a.status)}
            title={a.desc}
          >
            {a.label}
          </button>
        ))}
        {EXTRA_ACTIONS.map((a) =>
          (!a.only || incident.status === a.only) && incident.status !== "rejected" ? (
            <button
              key={a.label}
              className="btn"
              onClick={() => onAct(incident, a.status)}
              title={a.desc}
              style={{ color: "#f87171" }}
            >
              {a.label}
            </button>
          ) : null
        )}
      </div>
    </div>
  );
}
