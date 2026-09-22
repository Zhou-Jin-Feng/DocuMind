import { defineConfig, mergeConfig } from "vite";
import baseConfig from "./vite.config";

export default mergeConfig(
  baseConfig,
  defineConfig({
    define: {
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify(
        "http://127.0.0.1:4274",
      ),
      "import.meta.env.VITE_QUERY_REFRESH_INTERVAL_MS": JSON.stringify("30000"),
      "import.meta.env.VITE_FE01_PROFILE": JSON.stringify("1"),
    },
    build: {
      outDir: "../artifacts/frontend-3.1.0/fe03/profile-dist",
      emptyOutDir: true,
    },
  }),
);
