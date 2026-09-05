// What the toast says when a request fails. No browser, no server: `node --test`.
//
// Chad, 2026-09-05: "on walls and footings, if there is no footings, i have to
// put a '0' in every footing field." The 422 behind that read "Decimal input
// should be an integer, float, string or Decimal object" — and named no
// field, so nobody could tell which cell it meant. The schemas now take a
// blank as a zero (backend/tests/test_blank_cells_are_zero.py); this pins the
// other half — any 422 that still happens says which cell.

import { test } from "node:test";
import assert from "node:assert/strict";

// api.js reads `location` once at import time. Give it one first.
globalThis.location = { protocol: "http:", hostname: "localhost", port: "8001" };
const { describeFailure } = await import("../assets/js/api.js");

const DECIMAL = "Decimal input should be an integer, float, string or Decimal object";

test("a 422 on a grid row names the row and the cell", () => {
  const data = {
    detail: [{ type: "decimal_type", loc: ["body", "rows", 0, "ftg_width_in"], msg: DECIMAL, input: null }],
  };
  assert.equal(describeFailure("Unprocessable Entity", data), `row 1 ftg_width_in: ${DECIMAL}`);
});

test("several bad cells read one to a line, in order", () => {
  const data = {
    detail: [
      { type: "decimal_type", loc: ["body", "rows", 2, "mesh_sf"], msg: DECIMAL, input: null },
      { type: "greater_than_equal", loc: ["body", "rows", 2, "area_sf"], msg: "Input should be greater than or equal to 0", input: -1 },
    ],
  };
  assert.equal(
    describeFailure("Unprocessable Entity", data),
    `row 3 mesh_sf: ${DECIMAL}; row 3 area_sf: Input should be greater than or equal to 0`
  );
});

test("a 422 on a plain body field names the field", () => {
  const data = { detail: [{ type: "less_than_equal", loc: ["body", "margin_pct"], msg: "Input should be less than or equal to 2", input: 3 }] };
  assert.equal(describeFailure("Unprocessable Entity", data), "margin_pct: Input should be less than or equal to 2");
});

test("a 422 on a query parameter names it too", () => {
  const data = { detail: [{ type: "uuid_parsing", loc: ["query", "section_id"], msg: "Input should be a valid UUID", input: "nope" }] };
  assert.equal(describeFailure("Unprocessable Entity", data), "section_id: Input should be a valid UUID");
});

test("a string detail is the message as the server wrote it", () => {
  assert.equal(
    describeFailure("Bad Request", { detail: "a new row needs at least a length" }),
    "a new row needs at least a length"
  );
});

test("no detail at all falls back to the status text, then to a plain line", () => {
  assert.equal(describeFailure("Internal Server Error", null), "Internal Server Error");
  assert.equal(describeFailure("", "<html>gateway</html>"), "Request failed");
});
