// Basemap tile config — single source of truth for all maps in the app.
//
// Uses MapTiler (free tier, key in dashboard/.env as VITE_MAPTILER_KEY) and
// silently falls back to keyless CARTO dark tiles if the key is absent or
// removed, so the dashboard never breaks because of an expired key.
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY || "";

export const useMapTiler = Boolean(MAPTILER_KEY);

export const TILE_URL = useMapTiler
  ? `https://api.maptiler.com/maps/dataviz-dark/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`
  : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

export const TILE_ATTRIBUTION = useMapTiler
  ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://www.maptiler.com/">MapTiler</a>'
  : "&copy; OpenStreetMap contributors &copy; CARTO";

// MapTiler does not use {s} subdomains; Leaflet ignores it anyway, but keep
// maxZoom consistent across providers.
export const TILE_MAX_ZOOM = useMapTiler ? 20 : 19;
