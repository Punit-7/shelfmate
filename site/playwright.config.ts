import { defineConfig } from "@playwright/test";

// Run against the running site. Start it first: `docker compose up -d site` or `npm run dev`.
// Use PW_CHANNEL=msedge to drive an installed Edge; otherwise run `npx playwright install chromium` once.
export default defineConfig({
  testDir: "e2e",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    channel: process.env.PW_CHANNEL,
  },
  reporter: "list",
});
