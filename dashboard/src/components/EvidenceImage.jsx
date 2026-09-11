import { useEffect, useState } from "react";
import { BASE } from "../lib/api";

// Lazy evidence image: incidents no longer ship base64 in list responses
// (that multiplied pooler egress into GBs). Images are fetched on demand by
// id and cached, so popups/drawers only cost one small request each.
const cache = new Map(); // id -> data URL

export default function EvidenceImage({ id, hasImage, width, className, alt = "AI detection evidence" }) {
  const [src, setSrc] = useState(() => cache.get(id) || null);

  useEffect(() => {
    let alive = true;
    if (id && hasImage !== false && !cache.has(id)) {
      fetch(`${BASE}/incidents/${id}/image`)
        .then((r) => (r.ok ? r.blob() : null))
        .then((b) => {
          if (b && alive) {
            const url = URL.createObjectURL(b);
            cache.set(id, url);
            setSrc(url);
          }
        })
        .catch(() => {});
    } else if (cache.has(id)) {
      setSrc(cache.get(id));
    }
    return () => { alive = false; };
  }, [id, hasImage]);

  if (!src) return null;
  return <img src={src} width={width} className={className} style={{ borderRadius: 6 }} alt={alt} />;
}
