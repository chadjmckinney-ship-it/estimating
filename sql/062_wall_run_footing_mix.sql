-- 062_wall_run_footing_mix.sql
--
-- A footing can name its own mix.
--
-- Chad, 2026-09-05, ~7:30 AM, right after the section-level "Footing mix"
-- select went onto the walls page: "there is no option for me to set the mix
-- if I price walls manually" -- "per row footing mix, on the footing line."
--
-- The footing's mix now resolves in a ladder: this row's footing mix, else
-- the section's footing_mix_design_id (sql/040 -- the sheet's R8, one mix for
-- every footing), else the wall's own mix, so a footing never prices at
-- nothing. Every existing row is NULL and prices exactly as before. Same FK
-- shape as mix_design_id: retiring a mix design clears the reference rather
-- than blocking the delete.

ALTER TABLE wall_runs
    ADD COLUMN IF NOT EXISTS footing_mix_design_id integer
        REFERENCES mix_designs(id) ON DELETE SET NULL;

COMMENT ON COLUMN wall_runs.footing_mix_design_id IS
    'This footing''s mix (sql/062). NULL follows the section''s '
    'footing_mix_design_id, then the wall''s mix_design_id.';
