-- Remove drops that sql/022 duplicated.
--
-- The source workbook recorded drops twice: as a grade-beam type carrying the
-- real section and bar schedule (labelled "Drops (type 9)" on the LBJ import),
-- and again in the pour-level drops_ff total. sql/022 read drops_ff as the only
-- record and created a second beam per pour from it, so every one of those pours
-- now carries its drops twice for concrete and poly.
--
-- Rebar was unaffected — the migrated rows were written without a bar schedule.
--
-- Fix, per duplicated pour:
--   * delete the sql/022 placeholder row
--   * re-kind the real grade-beam row to kind='drop', which is what it is
--
-- Net effect: the drops driver behind forming and labor is unchanged (the same
-- footage, now carried by the real beam), concrete and poly stop being counted
-- twice, and those pours lose the invented 12x12 dimensions in favour of the
-- real section.
--
-- Placeholders with no counterpart are LEFT ALONE — on the Crunch Fitness
-- estimate drops_ff was genuinely the only record, so that row is the drops.
--
-- Stored calcs must be rewritten after applying:
--   curl -s -X POST localhost:8001/api/system-settings/recalc-all
--
-- Apply: psql -d estimating -f sql/024_dedupe_migrated_drops.sql

BEGIN;

-- Pair each placeholder with a same-pour, same-length real drop beam.
CREATE TEMP TABLE dup_drops ON COMMIT DROP AS
SELECT ph.id AS placeholder_id, real.id AS real_id
FROM grade_beams ph
JOIN grade_beams real
  ON real.mono_slab_id = ph.mono_slab_id
 AND real.id <> ph.id
 AND real.kind = 'grade_beam'
 AND real.label ILIKE 'Drops%'
 AND real.length_lf = ph.length_lf
WHERE ph.kind = 'drop'
  AND ph.label = 'Drop (migrated - verify W x H)';

DO $$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n FROM dup_drops;
    RAISE NOTICE 'duplicated drop pours found: %', n;
    IF n = 0 THEN
        RAISE NOTICE 'nothing to dedupe';
    END IF;
END $$;

-- The real beam becomes the drop it always was.
UPDATE grade_beams
SET kind = 'drop', updated_at = now()
WHERE id IN (SELECT real_id FROM dup_drops);

-- The invented one goes.
DELETE FROM grade_beams
WHERE id IN (SELECT placeholder_id FROM dup_drops);

-- Guard: no pour should end up with a placeholder still shadowing a real drop.
DO $$
DECLARE
    leftover int;
BEGIN
    SELECT count(*) INTO leftover
    FROM grade_beams ph
    JOIN grade_beams real
      ON real.mono_slab_id = ph.mono_slab_id
     AND real.id <> ph.id
     AND real.length_lf = ph.length_lf
     AND real.kind = 'drop'
    WHERE ph.label = 'Drop (migrated - verify W x H)';
    IF leftover > 0 THEN
        RAISE EXCEPTION 'Aborting: % placeholder(s) still shadow a real drop', leftover;
    END IF;
END $$;

COMMIT;
