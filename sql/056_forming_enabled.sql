-- 056_forming_enabled.sql
--
-- A forming line can be switched OFF.
--
-- Chad, 2026-09-04:
--
--   "there is one thing that is good and bad.. you have it set to that when
--    something shows an error if nothing is entered, I like that so I can
--    check it.. but that message should go away after I uncheck it as not
--    used"
--
-- Two halves to that, and this migration is the second one.
--
-- The first half was a bug in sql/053: the mobilization warning fired BECAUSE
-- the box was unchecked, so the one gesture meaning "considered, not needed"
-- was the one gesture that could not clear it. Code fix, no schema.
--
-- The second half is this. Labor lines and equipment lines have carried an
-- `enabled` flag and a checkbox since the beginning; forming lines never did.
-- So `RESHORING — forming` — a real quantity with no rate anywhere in the
-- system — sat in the unpriced list of every deck section with no box to
-- uncheck and no way to answer it. Same for a keyway you are not using, or
-- form release the sub brings.
--
-- A warning nobody can answer is a warning people learn to scroll past, and
-- the rest of the list loses its credibility with it. That list is the whole
-- point of this app.
--
-- TRUE for every existing row, which is what makes this a no-op: nothing is
-- switched off until somebody switches it off.

ALTER TABLE estimate_forming_lines
    ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN estimate_forming_lines.enabled IS
    'Include this line in the estimate. FALSE is a decision — the line keeps '
    'its quantity and its formula, extends at $0.00, and stops asking to be '
    'priced. Mirrors estimate_labor_lines.enabled and '
    'estimate_equipment_lines.enabled.';
