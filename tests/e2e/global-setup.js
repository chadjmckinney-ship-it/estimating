import fs from "node:fs";

import { request } from "@playwright/test";

/**
 * Sign in once for the whole run (sql/068) and store the session cookie where
 * playwright.config.js points storageState. Any role will do: the smoke suite
 * only reads. Without the two variables the spec skips itself.
 */
export default async function globalSetup(config) {
  const { E2E_USERNAME, E2E_PASSWORD } = process.env;
  if (!E2E_USERNAME || !E2E_PASSWORD) return;
  const baseURL = config.projects[0].use.baseURL;
  const ctx = await request.newContext({ baseURL, ignoreHTTPSErrors: true });
  const r = await ctx.post("/api/auth/login", {
    data: { username: E2E_USERNAME, password: E2E_PASSWORD },
  });
  if (!r.ok()) {
    throw new Error(`sign-in as ${E2E_USERNAME} failed: ${r.status()} ${await r.text()}`);
  }
  fs.mkdirSync("tests/e2e/.auth", { recursive: true });
  await ctx.storageState({ path: "tests/e2e/.auth/state.json" });
  await ctx.dispose();
}
