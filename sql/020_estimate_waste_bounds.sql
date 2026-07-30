-- Bound the estimate waste factors at the DB level (0–1, i.e. 0%–100%).
--
-- Why: EstimateUpdate accepted any numeric, so a PATCH of e.g. -1 was committed,
-- and every later read failed EstimateRead validation — 500ing not just that
-- estimate but the whole GET /api/estimates list. Schema bounds are fixed in
-- app/schemas/estimate.py; this makes the invariant hold for psql and any
-- future endpoint too. Mirrors estimates_form_percent_check (017).
--
-- Apply: psql -d estimating -f sql/020_estimate_waste_bounds.sql

BEGIN;

-- Fails loudly if any existing row is already out of range; inspect with:
--   SELECT id, name, waste_concrete, waste_sand, waste_rebar FROM estimates
--    WHERE waste_concrete NOT BETWEEN 0 AND 1
--       OR waste_sand     NOT BETWEEN 0 AND 1
--       OR waste_rebar    NOT BETWEEN 0 AND 1;

ALTER TABLE estimates
    DROP CONSTRAINT IF EXISTS estimates_waste_concrete_check;
ALTER TABLE estimates
    ADD CONSTRAINT estimates_waste_concrete_check
    CHECK (waste_concrete IS NULL OR (waste_concrete >= 0 AND waste_concrete <= 1));

ALTER TABLE estimates
    DROP CONSTRAINT IF EXISTS estimates_waste_sand_check;
ALTER TABLE estimates
    ADD CONSTRAINT estimates_waste_sand_check
    CHECK (waste_sand IS NULL OR (waste_sand >= 0 AND waste_sand <= 1));

ALTER TABLE estimates
    DROP CONSTRAINT IF EXISTS estimates_waste_rebar_check;
ALTER TABLE estimates
    ADD CONSTRAINT estimates_waste_rebar_check
    CHECK (waste_rebar IS NULL OR (waste_rebar >= 0 AND waste_rebar <= 1));

COMMENT ON COLUMN estimates.waste_concrete IS
    'Concrete waste factor 0–1 (0.05 = 5%). NULL = system_settings.waste_concrete.';
COMMENT ON COLUMN estimates.waste_sand IS
    'Sand waste factor 0–1. NULL = system_settings.waste_sand.';
COMMENT ON COLUMN estimates.waste_rebar IS
    'Rebar waste factor 0–1. NULL = system_settings.waste_rebar. '
    'NOTE: not yet applied by any calc — see docs/todo.md.';

COMMIT;
