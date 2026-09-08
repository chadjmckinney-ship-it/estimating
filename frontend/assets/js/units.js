/**
 * Unit conversion at the screen's edge.
 *
 * Every column in the database, the API and the engines speaks ONE unit — the
 * walls' footing width is inches, the sheet's N column — and a grid column may
 * still show another. Chad, 2026-09-08, on the spot footing grid: "you have
 * lf x w" x h", can we change it to width in feet?" A spread footing is called
 * out in feet (a 6'-0" square pad), so the box takes feet and the row keeps
 * inches; nothing behind the screen learns a second unit.
 *
 * A grid column carries `scale`: what a typed number is multiplied by on the
 * way to the row (feet × 12 → inches) and divided by on the way to the box.
 * No `scale`, or a scale of 1, is the plain box it always was — a typed
 * number goes through untouched, not rounded. Blank stays blank both ways: a
 * column the estimator has not measured is not a zero.
 */

/** What the box shows for a stored value: stored ÷ scale, to four places (54" → 4.5). */
export function toShown(stored, scale = 1) {
  if (stored == null || stored === "") return "";
  const n = Number(stored);
  if (!Number.isFinite(n)) return "";
  if (!scale || scale === 1) return n;
  return Math.round((n / scale) * 1e4) / 1e4;
}

/**
 * What the row stores for a typed value: typed × scale, to the column's three
 * places (4.333' → 51.996"). Scale 1 returns the number as typed — a $/SF
 * adder or a lb/SF rate must not come back rounded.
 */
export function toStored(typed, scale = 1, places = 3) {
  if (typed == null || typed === "") return null;
  const n = Number(typed);
  if (!Number.isFinite(n)) return null;
  if (!scale || scale === 1) return n;
  const p = 10 ** places;
  return Math.round(n * scale * p) / p;
}
