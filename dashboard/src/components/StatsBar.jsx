import React from "react";
import { labelIcon, labelColor, prettyLabel } from "../lib/labels.js";

export default function StatsBar({ stats }) {
  if (!stats) return null;

  const entries = Object.entries(stats.by_label).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));

  const kpis = [
    {
      icon: "📋",
      tone: "blue",
      value: stats.total,
      label: "Total Incidents",
    },
    {
      icon: "🚨",
      tone: "amber",
      value: stats.open,
      label: "Open Issues",
    },
    {
      icon: "✅",
      tone: "green",
      value: stats.resolved,
      label: "Resolved",
    },
    {
      icon: "📊",
      tone: "violet",
      value: stats.avg_severity,
      label: "Avg Severity / 10",
    },
    {
      icon: "📈",
      tone: "red",
      value: entries.length,
      label: "Issue Categories",
    },
  ];

  return (
    <div className="kpi-strip">
      {kpis.map((k) => (
        <div className="kpi" key={k.label}>
          <div className={`kpi-icon ${k.tone}`}>
            <span>{k.icon}</span>
          </div>
          <div>
            <div className="kpi-value">{k.value}</div>
            <div className="kpi-label">{k.label}</div>
          </div>
        </div>
      ))}
      {/* category breakdown as mini bars */}
      <div className="kpi" style={{ flex: 2.2, minWidth: 260 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 5 }}>
          {entries.slice(0, 4).map(([label, count]) => (
            <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, width: 108, color: "#94a3b8", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {labelIcon(label)} {prettyLabel(label)}
              </span>
              <div style={{ flex: 1, height: 5, background: "#1f2a3d", borderRadius: 3, overflow: "hidden" }}>
                <div style={{ width: `${(count / max) * 100}%`, height: "100%", background: labelColor(label), borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, width: 22, textAlign: "right" }}>{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
