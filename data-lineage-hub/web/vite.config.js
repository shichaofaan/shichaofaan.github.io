import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/dimensions": "http://127.0.0.1:8000",
      "/graph": "http://127.0.0.1:8000",
      "/ask": "http://127.0.0.1:8000",
      "/sync": "http://127.0.0.1:8000",
      "/doctor": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
