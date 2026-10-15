import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.VITE_DEV_API_TARGET ?? "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/health": { target: apiTarget, changeOrigin: true },
      "/ready": { target: apiTarget, changeOrigin: true },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 5180,
  },
});
