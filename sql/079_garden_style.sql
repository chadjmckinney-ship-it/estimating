-- 079_garden_style.sql
--
-- Garden style: a quantity on the pour. Chad, 2026-09-08: "garden-style
-- multiplier on the mono slab?" and, on the proposal, "yes, build it".
-- docs/specs/garden-style-spec.md.
--
-- The workbook's "Mono Slab on Grade Garden Style" tab is the 04 tab with a
-- QTY column (G): one row per BUILDING TYPE, taken off once, priced once, and
-- multiplied by the number of buildings of that type — University Hills is
-- five type rows covering eight buildings. The app had one shape for a pour
-- and no multiplier, so a garden-style job was eight rows that had to agree.
--
-- One integer does it: `qty`, default 1, on the pour row. The pour's stored
-- calc_* figures (concrete, sand, steel, cables, poly, the beam rollups) are
-- the ROW's totals — per-building geometry times qty — and every sum over
-- the raw takeoff columns (SF, perimeter, curb, thickened edge, demo, stair
-- treads, the paving adder, the beam lengths under the pour) carries the
-- multiplier the same way. A row at qty 8 is eight identical rows to the
-- cent; a row at qty 0 is on the list and in nothing.
--
-- Nothing existing moves: every pour on file gets qty 1.

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS qty integer NOT NULL DEFAULT 1;

ALTER TABLE mono_slabs
    DROP CONSTRAINT IF EXISTS mono_slabs_qty_nonneg;
ALTER TABLE mono_slabs
    ADD CONSTRAINT mono_slabs_qty_nonneg CHECK (qty >= 0);

COMMENT ON COLUMN mono_slabs.qty IS
    'Garden style (sql/079): how many of this pour the row stands for — the tab''s QTY (G). '
    'Default 1. The row''s calc_* figures and every section sum carry it; 0 keeps the row '
    'on the list and out of every total.';
