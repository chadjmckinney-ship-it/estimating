-- 059_footing_top_and_bottom_mats.sql
--
-- A footing's top and bottom mats can differ.
--
-- Chad, 2026-09-05, ~5:20 AM, looking at the wall grid freshly split into a
-- wall line and a footing line: "there are times with footings when the top
-- and bottom mat are different."
--
-- Until now the footing carried ONE bar set -- ftg_spacing_in, ftg_size -- and
-- a count, ftg_mats, that multiplied it. That is the workbook's shape (the 06
-- sheet's E*(N/P) + (E/P)*N terms times the mat count), right for LBJ, where
-- all 16 rows are #5 @ 12" top and bottom, and wrong for a footing with #5 @
-- 12" on the bottom and #4 @ 18" on top. Now each mat is its own (spacing,
-- size), on the deck's rule: a mat with no spacing or no size contributes
-- nothing, so a one-mat footing simply leaves the top blank.
--
-- Steel per mat is unchanged -- both directions, E*N/P each; see the comment
-- on calc_footing_rebar_lb -- and the footing's steel is the sum of its mats.
-- Two identical mats come to exactly what "2 mats" came to, so the reconciled
-- LBJ 33,727.83 lb does not move.
--
-- Backfill, from the live database on 2026-09-05: 17 wall runs. The 16 LBJ
-- rows all have ftg_mats = 2 with #5 @ 12", so the top becomes a copy of the
-- bottom. One test row has ftg_mats = 0 with zeros for spacing and size; a mat
-- count of 0 contributed nothing, so its bottom is cleared rather than
-- promoted to a real mat. No row has more than two mats; the guard below
-- refuses to run if one ever does, because there is no honest way to write
-- three mats into two.
--
-- Each step checks the catalog first, so the file is safe to run twice.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'wall_runs' AND column_name = 'ftg_mats')
       AND EXISTS (SELECT 1 FROM wall_runs WHERE ftg_mats > 2) THEN
        RAISE EXCEPTION '059: a wall run has more than two footing mats; there is no honest backfill for it';
    END IF;
END $$;

-- The old single bar set becomes the BOTTOM mat.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'wall_runs' AND column_name = 'ftg_spacing_in') THEN
        ALTER TABLE wall_runs RENAME COLUMN ftg_spacing_in TO ftg_bot_spacing_in;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'wall_runs' AND column_name = 'ftg_size') THEN
        ALTER TABLE wall_runs RENAME COLUMN ftg_size TO ftg_bot_size;
    END IF;
END $$;

ALTER TABLE wall_runs ADD COLUMN IF NOT EXISTS ftg_top_spacing_in numeric(8, 3);
ALTER TABLE wall_runs ADD COLUMN IF NOT EXISTS ftg_top_size       integer;

-- Two mats -> the top is a copy of the bottom. No mats -> no bottom either.
-- Then the count goes: with two named mats there is nothing left to count.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'wall_runs' AND column_name = 'ftg_mats') THEN
        UPDATE wall_runs
           SET ftg_top_spacing_in = ftg_bot_spacing_in,
               ftg_top_size       = ftg_bot_size
         WHERE ftg_mats >= 2;
        UPDATE wall_runs
           SET ftg_bot_spacing_in = NULL,
               ftg_bot_size       = NULL
         WHERE coalesce(ftg_mats, 0) = 0;
        ALTER TABLE wall_runs DROP COLUMN ftg_mats;
    END IF;
END $$;

COMMENT ON COLUMN wall_runs.ftg_bot_spacing_in IS
    'Bottom mat of the footing: bar spacing in inches, the same both '
    'directions. A mat with no spacing or no size contributes nothing (sql/059).';
COMMENT ON COLUMN wall_runs.ftg_bot_size IS
    'Bottom mat of the footing: bar size (#).';
COMMENT ON COLUMN wall_runs.ftg_top_spacing_in IS
    'Top mat of the footing: bar spacing in inches, the same both directions. '
    'Blank on a one-mat footing (sql/059).';
COMMENT ON COLUMN wall_runs.ftg_top_size IS
    'Top mat of the footing: bar size (#).';

COMMENT ON COLUMN wall_runs.calc_footing_rebar_lb IS
    'Both mats (sql/059), both directions each. Per mat the sheet adds E*(N/P) '
    'and (E/P)*N, which look like a copy-paste duplicate and are not: '
    'longitudinal bars are N/P bars each E ft long, transverse are E*12/P bars '
    'each N/12 ft long, and both come to E*N/P. Verified against the sheet. '
    'Do not "fix" it.';
