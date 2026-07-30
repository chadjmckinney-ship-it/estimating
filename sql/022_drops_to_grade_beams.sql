-- Retire mono_slabs.drops_ff — drops are now entered as grade beams (kind='drop').
--
-- The flat pour-level FF total only ever fed forming (2x4, bracing, ply) and the
-- labor DROPS line; it contributed no concrete, rebar or poly. Drops entered as
-- beams carry a real bar schedule and roll into the pour like GBs and Exp GBs,
-- so the field is redundant as an input — but it still holds the only copy of
-- the quantity, so it is migrated before being dropped.
--
-- Each pour with drops_ff > 0 becomes ONE drop-kind beam of that length.
--
--   *** WIDTH AND HEIGHT ARE PLACEHOLDERS ***
--   drops_ff recorded length only. 12 x 12 follows the one drop beam already
--   entered by hand ("Drop 1", 12x12). These rows are labelled
--   "Drop (migrated - verify W x H)" so they can be found and corrected:
--
--     SELECT * FROM grade_beams WHERE label LIKE 'Drop (migrated%';
--
--   Until corrected they add concrete CY and poly SF that the flat field never
--   counted: 12x12 = 0.0370 CY/LF before waste, and 2 SF/LF of poly wrap.
--   No bar schedule is written — steel is a per-drop design decision, and
--   inventing it on top of invented dimensions would compound the guess.
--
-- Forming and labor drivers now read sum(length_lf) WHERE kind='drop'
-- (app/services/forming.py, app/services/labor.py), so the quantities those
-- lines produce are unchanged by this migration.
--
-- Apply: psql -d estimating -f sql/022_drops_to_grade_beams.sql

BEGIN;

-- ------------------------------------------------------------- migrate ----

INSERT INTO grade_beams (
    mono_slab_id, kind, label,
    width_in, height_in, length_lf,
    notes, sort_order
)
SELECT
    m.id,
    'drop',
    'Drop (migrated - verify W x H)',
    12, 12, m.drops_ff,
    'Migrated from mono_slabs.drops_ff (' || m.drops_ff || ' FF). '
      || 'Length is the original figure; 12x12 is a placeholder - set the real '
      || 'section so concrete CY and poly SF are right.',
    900
FROM mono_slabs m
WHERE m.drops_ff IS NOT NULL
  AND m.drops_ff > 0
  -- re-runnable: skip pours that already have a migrated row
  AND NOT EXISTS (
      SELECT 1 FROM grade_beams gb
      WHERE gb.mono_slab_id = m.id
        AND gb.label = 'Drop (migrated - verify W x H)'
  );

-- Guard: every pour that had drops must now be represented in drop beams.
DO $$
DECLARE
    missing int;
BEGIN
    SELECT count(*) INTO missing
    FROM mono_slabs m
    WHERE m.drops_ff > 0
      AND NOT EXISTS (
          SELECT 1 FROM grade_beams gb
          WHERE gb.mono_slab_id = m.id AND gb.kind = 'drop'
      );
    IF missing > 0 THEN
        RAISE EXCEPTION 'Aborting: % pour(s) with drops_ff have no drop beam', missing;
    END IF;
END $$;

-- --------------------------------------------------------------- drop ----

ALTER TABLE mono_slabs DROP COLUMN IF EXISTS drops_ff;

COMMIT;
