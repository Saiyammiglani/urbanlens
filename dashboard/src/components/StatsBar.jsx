import React from "react";
import { labelIcon, labelColor, prettyLabel } from "../lib/labels.js";

export default function StatsBar({ stats }) {
  if (!stats) {
    // skeleton band while first load is in flight
    return (
      <div className="metricband" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div className={`kpi ${i === 0 ? "kpi-hero" : "kpi-mini"}`} key={i}>
            <div className="sk-line" style={{ width: "55%" }} />
            <div className="sk-line" style={{ width: "80%" }} />
          </div>
        ))}
      </div>
    );
  }

  const entries = Object.entries(stats.by_label).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));

  return (
    <div className="metricband">
      {/* hero — the number that matters most */}
      <div className="kpi kpi-hero">
        <span className="kpi-label">Open Issues</span>
        <div className="kpi-hero-row">
          <span className="kpi-value">{stats.open}</span>
        </div>
        <span className="kpi-hint">
          {stats.resolved} resolved · {stats.total} tracked
        </span>
      </div>

      {/* minis */}
      <div className="kpi kpi-mini">
        <span className="kpi-label">Total Incidents</span>
        <span className="kpi-value">{stats.total}</span>
        <span className="kpi-hint">all time</span>
      </div>
      <div className="kpi kpi-mini">
        <span className="kpi-label">Resolved</span>
        <span className="kpi-value tone-ok">{stats.resolved}</span>
        <span className="kpi-hint">closed by crews</span>
      </div>
      <div className="kpi kpi-mini">
        <span className="kpi-label">Avg Severity</span>
        <span className={`kpi-value ${stats.avg_severity >= 7 ? "tone-danger" : stats.avg_severity >= 4 ? "tone-warn" : "tone-ok"}`}>
          {stats.avg_severity.toFixed(1)}
        </span>
        <span className="kpi-hint">out of 10</span>
      </div>
      <div className="kpi kpi-mini">
        <span className="kpi-label">Categories</span>
        <span className="kpi-value">{entries.length}</span>
        <span className="kpi-hint">issue types</span>
      </div>

      {/* issue mix */}
      <div className="metric-mix">
        <span className="kpi-label">Issue Mix</span>
        {entries.slice(0, 4).map(([label, count]) => (
          <div className="mix-row" key={label}>
            <span className="mix-name">{labelIcon(label)} {prettyLabel(label)}</span>
            <div className="mix-track">
              <div className="mix-fill" style={{ width: `${(count / max) * 100}%`, background: labelColor(label) }} />
            </div>
            <span className="mix-count">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
