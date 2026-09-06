// Supabase Realtime client — instant map pings without polling.
// Falls back silently to the existing 4-second poll if realtime drops.
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "";
const SUPABASE_ANON = import.meta.env.VITE_SUPABASE_ANON || "";

let client = null;

export function realtimeAvailable() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON);
}

/**
 * Subscribe to inserts on the given tables; each event fires cb(table, row).
 * Safe to call multiple times (React StrictMode double-mount) — each call
 * gets its own channels and its own unsubscribe function.
 */
export function subscribeRealtime(tables, cb) {
  if (!realtimeAvailable()) return () => {};

  client = client || createClient(SUPABASE_URL, SUPABASE_ANON, {
    realtime: { params: { eventsPerSecond: 20 } },
  });

  const channels = tables.map((table) =>
    client
      .channel(`public:${table}`)
      .on("postgres_changes",
        { event: "INSERT", schema: "public", table },
        (payload) => {
          try { cb(table, payload.new); } catch {}
        })
      .subscribe()
  );

  console.info("[realtime] subscribed:", tables.join(", "));
  return () => channels.forEach((c) => client?.removeChannel(c));
}
