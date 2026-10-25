import { defineConfig } from "vite";
import { env } from "node:process";

const api = env.BA_TEST_API_URL || "http://127.0.0.1:8000";

export default defineConfig({
  server: {
    proxy: {
      "/api": api,
      "/healthz": api,
    },
  },
});
