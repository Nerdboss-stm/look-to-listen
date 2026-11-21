/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly REPO_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
