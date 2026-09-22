/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_QUERY_REFRESH_INTERVAL_MS?: string;
  readonly VITE_FE01_PROFILE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
