// Shared label taxonomy + colors + helpers

export const LABEL_META = {
  pothole: { color: "#ef4444", icon: "🕳️" },
  crack: { color: "#f97316", icon: "⚡" },
  waterlogging: { color: "#3b82f6", icon: "💧" },
  garbage_dump: { color: "#84cc16", icon: "🗑️" },
  illegal_parking: { color: "#eab308", icon: "🚗" },
  broken_streetlight: { color: "#a855f7", icon: "💡" },
  open_manhole: { color: "#ec4899", icon: "⭕" },
  roadside_debris: { color: "#14b8a6", icon: "🧱" },
  faded_signage: { color: "#94a3b8", icon: "🪧" },
};

export const FALLBACK_COLOR = "#f59e0b";

export function labelColor(label) {
  return LABEL_META[label]?.color || FALLBACK_COLOR;
}

export function labelIcon(label) {
  return LABEL_META[label]?.icon || "⚠️";
}

export function prettyLabel(label) {
  return (label || "").replace(/_/g, " ");
}

export function sevClass(sev) {
  return sev >= 8 ? "high" : sev >= 5 ? "mid" : "low";
}

export function statusClass(status) {
  return `status-${status}`;
}

export function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function severityRadius(sev) {
  return 5 + sev * 1.8;
}
