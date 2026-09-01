import React, { useState } from "react";
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

function sevTag(sev) {
  return sev >= 8 ? "Critical" : sev >= 5 ? "Warning" : "Low";
}

export default function IncidentFeed({ incidents, loading, selected, onSelect, onAct, onHover, variant = "panel" }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const shown = q
    ? incidents.filter((i) =>
        i.label.toLowerCase().includes(q) ||
        (i.assigned_dept || "").toLowerCase().includes(q) ||
        i.status.toLowerCase().includes(q) ||
        i.id.slice(0, 8).includes(q)
      )
    : incidents;

  return (
    <aside className={`panel ${variant === "full" ? "full" : ""}`}>
      <div className="panel-head">
        <div className="panel-title-row">
          <div className="panel-title">
            Incidents
            <span className="sidebar-count">{incidents.length}</span>
          </div>
        </div>

        <div className="sidebar-search">
          <span className="search-icon" aria-hidden="true">🔍</span>
          <input
            className="search-input"
            type="text"
            placeholder="Search type, dept, status, ID…"
            aria-label="Search incidents"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="search-clear" onClick={() => setQuery("")} title="Clear">✕</button>
          )}
        </div>
      </div>

      <div className="feed-list" role="list">
        {loading && incidents.length === 0 &&
          [0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="card skeleton" aria-hidden="true">
              <div className="sk-line" style={{ width: "38%" }} />
              <div className="sk-line" style={{ width: "72%" }} />
              <div className="sk-line" style={{ width: "52%" }} />
            </div>
          ))}

        {!loading && incidents.length === 0 && (
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

        {shown.length === 0 && incidents.length > 0 && (
          <div className="empty">
            <div className="icon">🔍</div>
            <h3>No matches for “{query}”</h3>
            <p>Try a different keyword — issue type, department, status or incident ID.</p>
          </div>
        )}

        {shown.map((inc) => {
          const next = NEXT_ACTION[inc.status];
          const c = labelColor(inc.label);
          return (
            <div
              key={inc.id}
              className={`card ${selected?.id === inc.id ? "selected" : ""} ${
                inc.status === "resolved" || inc.status === "rejected" ? "resolved" : ""
              }`}
              style={{ "--card-accent": c }}
              onClick={() => onSelect(inc)}
              onMouseEnter={() => onHover?.(inc.id)}
              onMouseLeave={() => onHover?.(null)}
            >
              <div className="card-top">
                <span className={`sev-badge ${sevClass(inc.severity)}`}>
                  Sev {inc.severity} · {sevTag(inc.severity)}
                </span>
                <span className="card-time">{timeAgo(inc.created_at)}</span>
              </div>

              <div className="card-title">
                <span className="ticon">{labelIcon(inc.label)}</span>
                {prettyLabel(inc.label)}
              </div>
              <div className="card-dept">{inc.assigned_dept || "Unassigned"}</div>
              <div className="card-loc">{inc.lat.toFixed(5)}, {inc.lon.toFixed(5)}</div>

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
