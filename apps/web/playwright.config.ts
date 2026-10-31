import { defineConfig } from "@playwright/test";
import { env } from "node:process";

const real = env.BA010_REAL === "1";
export default defineConfig({
  testDir: "./e2e",
  testMatch: real ? ["real.spec.ts", "u06.real.spec.ts"] : "*mock.spec.ts",
  outputDir: real ? "test-results/real" : "test-results/mock",
  timeout: real ? 360_000 : 45_000,
  workers: 1,
  retries: 0,
  use: {
    baseURL: real
      ? env.BA_TEST_WEB_URL || "http://localhost:5173"
      : "http://127.0.0.1:4173",
    viewport: { width: 1440, height: 1050 },
    // Traces/HAR can contain guest credentials; do not record them.
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
    launchOptions: {
      args: [
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
      ],
    },
  },
  webServer: real
    ? undefined
    : {
        command: "npm run dev -- --port 4173",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: false,
      },
});
