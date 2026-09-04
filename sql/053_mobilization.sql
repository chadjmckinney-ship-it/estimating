-- 053_mobilization.sql
--
-- Mobilization: getting the iron to the job and home again.
--
-- Chad, 2026-09-04, while settling the deck's crane rate: **"we need to add a
-- price for mobilization."**
--
-- ---------------------------------------------------------------------------
-- The workbook has never priced it
-- ---------------------------------------------------------------------------
--
-- Every tab of the LBJ workbook was searched for "mobil", "demob", "delivery"
-- and "haul in". Eight hits, and all eight are noise: six say "Mobile" beside
-- a supplier's phone number on the Pricing tab, and two are a box delivery
-- line on the PT slab sheets.
--
-- So this is not a formula being reproduced. It is a real cost the sheets have
-- been leaving out — on a job with a $3,200/day crane on it, that is not a
-- rounding error — and every decision below is Chad's rather than the
-- workbook's.
--
-- ---------------------------------------------------------------------------
-- The three decisions
-- ---------------------------------------------------------------------------
--
-- 1. **One line per SECTION**, not per machine and not per job. Asked where
--    mobilization should live: *one line per section*. So it joins the
--    contract-services block on every assembly, beside FREIGHT and OUT OF
--    TOWN EXPENSE — a rate and a count, typed where the work is.
--
--    Per-machine (a column on the equipment catalog) is still reachable from
--    here if a job ever needs it: the line would just sum the machines instead
--    of being typed. Nothing below forecloses it.
--
-- 2. **One round-trip number.** Not a mobilize figure and a demobilize figure.
--    `rate` is what a move costs both ways; `days_qty` is HOW MANY MOVES, so a
--    job that mobilizes twice for two phases says 2 rather than doubling a
--    number in somebody's head.
--
-- 3. **Neither taxed nor fuelled.** It is a haul, which is work done rather
--    than a thing bought — the same call sql/036 made for concrete haul-off,
--    and the same treatment pumping, saw cutting and freight already get. The
--    line sits in the `contract` group, and `costing._on_takeoff_lines`
--    classifies by group, so this is a property of where it lives rather than
--    a special case anybody has to remember.
--
-- ---------------------------------------------------------------------------
-- Why this migration carries no number
-- ---------------------------------------------------------------------------
--
-- sql/044 and claude/design-decisions.md: prices live in the catalog and on
-- the estimate's price sheet, never in a migration. A mobilization figure
-- committed here would be a second home for a price, and the second home is
-- the one nobody updates.
--
-- So the KEY is created and the VALUE is jsonb null. That is deliberate and it
-- is three things at once:
--
--   * the key exists, so it can be edited and so it appears on a price sheet
--     the moment it has a number;
--   * `#>> '{}'` on a jsonb null is SQL NULL, so `_setting_numeric` falls
--     through to the caller's default and `_rate_optional` returns None —
--     UNPRICED, not free (design decision 5, "a zero rate is a statement");
--   * sql/049's settings backfill has a numeric guard, so a null is skipped
--     rather than copied onto every estimate's sheet as a zero.
--
-- The section says "mobilization — not entered" whenever it bills rental days
-- and this line is zero. A warning, not a refusal — Chad, on validation:
-- "Skip it." A job really can have no mobilization (equipment already on
-- site from the last phase); it should just never be SILENT.

INSERT INTO system_settings (key, value, description) VALUES
    ('mobilization_ls', 'null'::jsonb,
     'Round-trip cost of one mobilization: getting the equipment to the job '
     'and home again. Deliberately unset — there is no company number for '
     'this yet, and an invented one would be worse than a warning. Set it '
     'here to seed every new section, or type it on the section''s '
     'MOBILIZATION line. Untaxed and no fuel & maintenance: it is a haul.')
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE system_settings IS
    'Company-wide rates and rules. A key whose value is jsonb null EXISTS but '
    'is unpriced — readable, editable, and reported as missing rather than '
    'read as zero (sql/053).';
