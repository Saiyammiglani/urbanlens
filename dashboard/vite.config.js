import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    allowedHosts: true, // public demo tunnels (trycloudflare.com etc.)
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
