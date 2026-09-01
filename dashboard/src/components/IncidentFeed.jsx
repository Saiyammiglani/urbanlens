import React from "react";
import {
  labelColor,
  labelIcon,
  prettyLabel,
  sevClass,
  statusClass,
  timeAgo,
} from "../lib/labels.js";

// next workflow action per status
const NEXT_ACTION = {
  new: { status: "confirmed", label: "Confirm" },
  confirmed: { status: "assigned", label: "Assign" },
  assigned: { status: "in_progress", label: "Start Work" },
  in_progress: { status: "resolved", label: "Mark Resolved" },
  resolved: { status: "in_progress", label: "Reopen" },
  rejected: { status: "confirmed", label: "Re-verify" },
};

export default function IncidentFeed({ incidents, selected, onSelect, onAct }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <div className="sidebar-title">
          Incident Queue
          <span className="sidebar-count">{incidents.length}</span>
        </div>
      </div>

      <div className="feed-list">
        {incidents.length === 0 && (
          <div className="empty">
            <div className="icon">🛰️</div>
            <h3>No incidents detected yet</h3>
            <p>
              Start the fleet simulator to generate live detections:
              <br />
              <code>python scripts/simulate_fleet.py</code>
            </p>
          </div>
        )}

        {incidents.map((inc) => {
          const next = NEXT_ACTION[inc.status];
          return (
            <div
              key={inc.id}
              className={`card ${selected?.id === inc.id ? "selected" : ""} ${
                inc.status === "resolved" || inc.status === "rejected" ? "resolved" : ""
              }`}
              onClick={() => onSelect(inc)}
            >
              <div className="card-strip" style={{ background: labelColor(inc.label) }} />

              <div className="card-head">
                <span className="card-type" style={{ color: labelColor(inc.label) }}>
                  {labelIcon(inc.label)} {prettyLabel(inc.label)}
                </span>
                <span className={`sev-badge ${sevClass(inc.severity)}`}>
                  SEV {inc.severity}
                </span>
              </div>

              <div className="card-meta">
                <span className={`status-badge ${statusClass(inc.status)}`}>
                  {prettyLabel(inc.status)}
                </span>
                <span className="meta-item">
                  <span className="conf-bar">
                    <span
                      className="conf-fill"
                      style={{ width: `${Math.round(inc.confidence * 100)}%`, display: "block" }}
                    />
                  </span>
                  {Math.round(inc.confidence * 100)}%
                </span>
                <span className="meta-item">👁 {inc.observation_count}×</span>
                <span className="meta-item">🕐 {timeAgo(inc.created_at)}</span>
              </div>

              <div className="card-foot">
                <span className="card-dept">{inc.assigned_dept || "Unassigned"}</span>
                {next && (
                  <div className="card-actions" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => onAct(inc, next.status)}>{next.label}</button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
