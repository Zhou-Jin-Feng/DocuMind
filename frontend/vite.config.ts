/// <reference types="vitest/config" />

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_FE01_PROFILE": JSON.stringify("0"),
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
  test: {
    exclude: ["benchmarks/**", "e2e/**", "e2e-real/**", "node_modules/**", "dist/**"],
  },
});
