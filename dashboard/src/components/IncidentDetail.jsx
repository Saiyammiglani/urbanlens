import React, { useEffect, useState } from "react";
import EvidenceImage from "./EvidenceImage";
import {
  labelColor,
  labelIcon,
  prettyLabel,
  statusClass,
  timeAgo,
} from "../lib/labels.js";

const WORKFLOW = [
  { status: "confirmed",  label: "Confirm",      icon: "✓", desc: "Validate the AI detection" },
  { status: "assigned",   label: "Assign",        icon: "→", desc: "Route to responsible department" },
  { status: "in_progress",label: "Start Work",    icon: "⚙", desc: "Crew is dispatched on site" },
  { status: "resolved",   label: "Mark Resolved", icon: "✔", desc: "Issue fixed & verified" },
];
const EXTRA_ACTIONS = [
  { status: "rejected",   label: "Reject",        icon: "✗", desc: "False positive / invalid detection", danger: true },
  { status: "in_progress",label: "Reopen",        icon: "↺", desc: "Issue has recurred", only: "resolved" },
];

const ALLOWED = {
  new:         ["confirmed", "rejected"],
  confirmed:   ["assigned",  "rejected"],
  assigned:    ["in_progress","rejected"],
  in_progress: ["resolved",  "rejected"],
  resolved:    ["in_progress"],
  rejected:    ["confirmed"],
};

function SevBar({ value }) {
  const color = value >= 8 ? "#f87171" : value >= 5 ? "#fbbf24" : "#34d399";
  const label = value >= 8 ? "CRITICAL" : value >= 5 ? "HIGH" : "LOW";
  return (
    <div className="ev-sev">
      <div className="ev-sev-header">
        <span className="ev-sev-label">Severity</span>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span className="ev-sev-tag" style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}>{label}</span>
          <span className="ev-sev-num" style={{ color }}>{value} <span style={{ color: "var(--tx-3)", fontWeight: 400 }}>/ 10</span></span>
        </div>
      </div>
      <div className="ev-sev-track">
        <div className="ev-sev-fill" style={{ width: `${value * 10}%`, background: color, boxShadow: `0 0 10px ${color}50` }} />
      </div>
    </div>
  );
}

function StatusProgress({ current }) {
  const STEPS = ["new", "confirmed", "assigned", "in_progress", "resolved"];
  const rejected = current === "rejected";
  const currentIdx = STEPS.indexOf(current);

  return (
    <div className="ev-progress">
      <div className="ev-progress-label">Status Pipeline</div>
      {rejected ? (
        <div className="ev-rejected-banner">
          <span>✗</span> Rejected — marked as false positive
        </div>
      ) : (
        <div className="ev-steps">
          {STEPS.map((step, i) => {
            const done  = currentIdx > i;
            const active = currentIdx === i;
            const future = currentIdx < i;
            return (
              <React.Fragment key={step}>
                <div className={`ev-step ${done ? "done" : active ? "active" : "future"}`}>
                  <div className="ev-step-dot">
                    {done ? "✓" : active ? "●" : ""}
                  </div>
                  <div className="ev-step-name">{prettyLabel(step)}</div>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`ev-step-line ${done ? "done" : ""}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function IncidentDetail({ incident, onClose, onAct }) {
  const [address, setAddress] = useState(incident?.address || null);
  const [imgExpanded, setImgExpanded] = useState(false);

  useEffect(() => {
    if (!incident) return;
    let alive = true;
    setAddress(incident.address || null);
    setImgExpanded(false);
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
  const allActions = [...WORKFLOW, ...EXTRA_ACTIONS].filter((a) => !a.only || incident.status === a.only);

  return (
    <div className="evidence-panel" style={{ "--accent": c }}>
      {/* ── Header ── */}
      <div className="ev-header" style={{ borderBottom: `1px solid ${c}22` }}>
        <div className="ev-header-left">
          <div className="ev-type-badge" style={{ background: `${c}14`, border: `1px solid ${c}30`, color: c }}>
            {labelIcon(incident.label)} {prettyLabel(incident.label)}
          </div>
          <div className="ev-id-row">
            <span className="ev-dept">{incident.assigned_dept || "Unassigned"}</span>
            <span className="ev-id-sep">·</span>
            <span className="ev-id">#{incident.id.slice(0, 8).toUpperCase()}</span>
          </div>
        </div>
        <button className="ev-close" onClick={onClose} aria-label="Close evidence panel">
          <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <path d="M1 1l12 12M13 1L1 13" />
          </svg>
        </button>
      </div>

      <div className="ev-body">
        {/* ── Evidence Image ── */}
        <div className="ev-section">
          <div className="ev-section-label">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>
            Evidence Capture
          </div>
          {incident.has_image || incident.image_b64 ? (
            <div className={`ev-img-wrap ${imgExpanded ? "expanded" : ""}`} onClick={() => setImgExpanded(!imgExpanded)}>
              <EvidenceImage id={incident.id} className="ev-img" />
              <div className="ev-img-overlay">
                <div className="ev-img-conf" style={{ background: `${c}cc` }}>
                  {prettyLabel(incident.label)} · {Math.round(incident.confidence * 100)}%
                </div>
                <div className="ev-img-zoom">{imgExpanded ? "⊖ Click to shrink" : "⊕ Click to expand"}</div>
              </div>
            </div>
          ) : (
            <div className="ev-img-none">
              <span>📷</span>
              <span>No image captured — GPS-only detection</span>
            </div>
          )}
        </div>

        {/* ── Severity ── */}
        <div className="ev-section">
          <SevBar value={incident.severity} />
        </div>

        {/* ── Metrics grid ── */}
        <div className="ev-section">
          <div className="ev-section-label">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3v18h18" /><path d="M7 16l4-4 3 3 5-5" /></svg>
            Detection Metrics
          </div>
          <div className="ev-grid">
            <div className="ev-cell">
              <div className="ev-cell-label">Confidence</div>
              <div className="ev-cell-value" style={{ color: Math.round(incident.confidence * 100) >= 80 ? "#34d399" : "#fbbf24" }}>
                {Math.round(incident.confidence * 100)}%
              </div>
              <div className="ev-cell-bar">
                <div style={{ width: `${incident.confidence * 100}%`, background: Math.round(incident.confidence * 100) >= 80 ? "#34d399" : "#fbbf24", height: "100%", borderRadius: 2 }} />
              </div>
            </div>
            <div className="ev-cell">
              <div className="ev-cell-label">Sightings</div>
              <div className="ev-cell-value">{incident.observation_count}<span style={{ fontSize: 11, color: "var(--tx-3)", fontWeight: 400 }}>×</span></div>
            </div>
            <div className="ev-cell">
              <div className="ev-cell-label">First Seen</div>
              <div className="ev-cell-value small">{timeAgo(incident.created_at)}</div>
            </div>
            <div className="ev-cell">
              <div className="ev-cell-label">Status</div>
              <div className="ev-cell-value">
                <span className={`status-badge ${statusClass(incident.status)}`}>{prettyLabel(incident.status)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Location ── */}
        <div className="ev-section">
          <div className="ev-section-label">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" /><circle cx="12" cy="9" r="2.5" /></svg>
            Location
          </div>
          <div className="ev-location">
            {address && <div className="ev-address">📍 {address}</div>}
            <div className="ev-coords">{incident.lat.toFixed(5)}, {incident.lon.toFixed(5)}</div>
          </div>
        </div>

        {/* ── Status Pipeline ── */}
        <div className="ev-section">
          <StatusProgress current={incident.status} />
        </div>

        {/* ── Actions ── */}
        <div className="ev-section">
          <div className="ev-section-label">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
            Actions
          </div>
          <div className="ev-actions">
            {allActions.map((a) => {
              const legal = (ALLOWED[incident.status] || []).includes(a.status);
              return (
                <button
                  key={a.label}
                  className={`ev-action-btn ${legal ? (a.danger ? "danger" : "primary") : "disabled"}`}
                  onClick={() => legal && onAct(incident, a.status)}
                  disabled={!legal}
                  title={legal ? a.desc : `Not allowed from "${prettyLabel(incident.status)}"`}
                >
                  <span className="ev-action-icon">{a.icon}</span>
                  {a.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
