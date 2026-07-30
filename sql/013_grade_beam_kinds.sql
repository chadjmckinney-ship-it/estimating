-- Mono-slab beam kinds: grade beams, exposed GBs, drops (Excel 04 pour columns)
-- Parent remains mono_slabs — not estimate-level 02-Gd Beams.
-- Apply: psql -d estimating -f sql/013_grade_beam_kinds.sql

BEGIN;

-- Drop the mistaken estimate-level exposed table (scaffold only; re-model under pours)
DROP TABLE IF EXISTS exposed_grade_beams;

ALTER TABLE grade_beams
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'grade_beam';

-- Backfill any nulls (IF NOT EXISTS path on re-run)
UPDATE grade_beams SET kind = 'grade_beam' WHERE kind IS NULL OR kind = '';

ALTER TABLE grade_beams
    DROP CONSTRAINT IF EXISTS grade_beams_kind_check;

ALTER TABLE grade_beams
    ADD CONSTRAINT grade_beams_kind_check
    CHECK (kind IN ('grade_beam', 'exposed', 'drop'));

CREATE INDEX IF NOT EXISTS grade_beams_mono_slab_kind_idx
    ON grade_beams (mono_slab_id, kind);

COMMENT ON COLUMN grade_beams.kind IS
    'Excel 04 pour role: grade_beam | exposed (EXP GB) | drop — same bar schedule shape';

COMMIT;
