// Where the SPA sends its requests. No browser, no server: `node --test`.
//
// Until 2026-09-04 api.js sent any localhost port other than 8001 to
// 127.0.0.1:8001 — so `run.ps1 -Port 8002`, the natural move when 8001 is
// busy, rendered a page whose every write went to whatever old process was
// still on 8001 (audit P2 #10). The rule now is the obvious one: a page a
// server handed you talks to that server; only a page opened from disk has
// no origin and still points at the dev host.

import { test } from "node:test";
import assert from "node:assert/strict";

// api.js reads `location` once at import time. Give it one first.
globalThis.location = { protocol: "http:", hostname: "localhost", port: "8002" };
const { apiBaseFor } = await import("../assets/js/api.js");

test("a page a server handed you talks to that server, whatever the port", () => {
  for (const loc of [
    { protocol: "http:", hostname: "127.0.0.1", port: "8001" },
    { protocol: "http:", hostname: "localhost", port: "8001" },
    { protocol: "http:", hostname: "127.0.0.1", port: "8002" },
    { protocol: "http:", hostname: "localhost", port: "5173" },
    { protocol: "http:", hostname: "192.168.1.40", port: "8001" },
    { protocol: "https:", hostname: "estimating.office", port: "" },
  ]) {
    assert.equal(apiBaseFor(loc), "/api", JSON.stringify(loc));
  }
});

test("a page opened straight from disk still finds the dev host", () => {
  assert.equal(
    apiBaseFor({ protocol: "file:", hostname: "", port: "" }),
    "http://127.0.0.1:8001/api"
  );
});
