import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/react/" : "/",
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [path.resolve(root, ".."), path.resolve(root, "../app")] },
    proxy: {
      "/react/api": "http://localhost:8000",
      "/static": "http://localhost:8000",
      "/login": "http://localhost:8000",
      "/logout": "http://localhost:8000",
    },
  },
  build: {
    outDir: path.resolve(root, "../app/url_short/static/react"),
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: (asset) => asset.names?.some((name) => name.endsWith(".css")) ? "app.css" : "assets/[name]-[hash][extname]",
      },
    },
  },
}));
