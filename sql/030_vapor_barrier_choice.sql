-- 030: name the vapor barrier instead of guessing it
--
-- costing._poly_cost searched the catalog for a name containing "10 mil" and
-- "20", which found "POLY 10 mil 20 x 100 Black" at $105/roll — $0.0525/SF —
-- and priced the LBJ job with it. The job was bid on 10 mil Yellow Guard at
-- $0.125/SF, and Yellow Guard could never win that search at any price: its
-- name has no "20" in it. $9,008 on one job.
--
-- The picked roll is not even in the vapor_barrier category; it sits in
-- site_accessories. Nothing about the match was meaningful.
--
-- Resolution order after this: the estimate's choice, else the company default,
-- else the old name search (so nothing breaks on estimates nobody has set).

BEGIN;

ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS vapor_barrier_material_id integer
    REFERENCES materials(id) ON DELETE SET NULL;

COMMENT ON COLUMN estimates.vapor_barrier_material_id IS
    'Vapor barrier product for this job. NULL falls back to the company default.';

INSERT INTO system_settings (key, value, description) VALUES
    ('default_vapor_barrier_material_id', '0'::jsonb,
     'materials.id of the default vapor barrier. 0 = fall back to name matching.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
