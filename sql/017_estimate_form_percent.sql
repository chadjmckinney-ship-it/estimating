-- Per-estimate % of forming (Excel W65) — applies only to form lumber lines
-- Apply: psql -d estimating -f sql/017_estimate_form_percent.sql

BEGIN;

ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS form_percent numeric(6, 4);

ALTER TABLE estimates
    DROP CONSTRAINT IF EXISTS estimates_form_percent_check;

ALTER TABLE estimates
    ADD CONSTRAINT estimates_form_percent_check
    CHECK (form_percent IS NULL OR (form_percent >= 0 AND form_percent <= 2));

COMMENT ON COLUMN estimates.form_percent IS
    'Excel “% of forming” for this estimate. NULL = system_settings.form_percent (default 0.50). '
    'Applies only to form lumber: 2x4, 2x6, 2x10, forming ply, masonite/siding — not nails, stakes, anchors, etc.';

-- Seed LBJ-style default on existing estimates that already have forming summary
UPDATE estimates e
SET form_percent = s.form_percent
FROM estimate_forming_summary s
WHERE s.estimate_id = e.id
  AND e.form_percent IS NULL
  AND s.form_percent IS NOT NULL;

COMMIT;
