// A grid box typed in one unit, a row stored in another. No browser: `node --test`.
//
// The spot footing's width (2026-09-08): the box takes feet, the row keeps the
// walls' inches, and the two functions in units.js are the only place the
// twelve lives. Float slop is the thing to pin — 0.1 × 12 is
// 1.2000000000000002 in IEEE-754, and a row that stores that is a row nobody
// typed.

import { test } from "node:test";
import assert from "node:assert/strict";

const { toShown, toStored } = await import("../assets/js/units.js");

test("a stored width in inches shows as feet", () => {
  assert.equal(toShown(54, 12), 4.5);
  assert.equal(toShown("120.000", 12), 10); // the API's fixed-scale decimal
  assert.equal(toShown(51.996, 12), 4.333);
  assert.equal(toShown(0, 12), 0);
});

test("a typed width in feet stores as inches, to the column's three places", () => {
  assert.equal(toStored(4.5, 12), 54);
  assert.equal(toStored(10, 12), 120);
  assert.equal(toStored(4.25, 12), 51);
  assert.equal(toStored(4.333, 12), 51.996);
  assert.equal(toStored(0.1, 12), 1.2); // not 1.2000000000000002
});

test("feet in, feet out", () => {
  for (const ft of [4.5, 10, 4.333, 6.25, 0.75]) {
    assert.equal(toShown(toStored(ft, 12), 12), ft);
  }
});

test("no scale is the plain box: nothing rounded, nothing touched", () => {
  assert.equal(toStored(1.2345), 1.2345);
  assert.equal(toStored(0.0825, 1), 0.0825);
  assert.equal(toShown(187752.0), 187752);
  assert.equal(toShown("2942.000"), 2942);
});

test("blank stays blank both ways — an unmeasured column is not a zero", () => {
  assert.equal(toShown(null, 12), "");
  assert.equal(toShown("", 12), "");
  assert.equal(toShown("abc", 12), "");
  assert.equal(toStored(null, 12), null);
  assert.equal(toStored("", 12), null);
  assert.equal(toStored("abc", 12), null);
});
