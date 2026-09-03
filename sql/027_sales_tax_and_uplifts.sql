-- 027: sales tax, equipment fuel & maintenance, tie-steel allowance
--
-- Found by reconciling estimate "04-PT Slab on Grade" against
-- workbooks/Downloads/Trammel Crow - LBJ Estimate.xlsm. Three rules the
-- workbook prices with that had no home in this system:
--
--   1. Sales tax on materials — 8.25%, cell Y44, with an EXEMPT toggle.
--      Understated that one job by $37,778.
--   2. Fuel & maintenance on equipment rentals — 50%, cell J98. Understated
--      the same job by $12,058.
--   3. Tie steel is paid only on rebar weight ABOVE 0.35 lb/SF (column U:
--      IF(P-(D*0.35)<0,0,P-(D*0.35))). Billing all tonnage overstated labor
--      by $6,075.
--
-- Tax is stored per pour rather than folded into unit costs: the catalog stays
-- pre-tax so it reads as a real material list, and an estimator can see the tax
-- line. Exemption is per project — ROW paving is always exempt.

BEGIN;

-- Per-project exemption. Tax is charged unless the project says otherwise.
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS tax_exempt boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN projects.tax_exempt IS
    'No sales tax on materials for this project. Always true for ROW paving.';

-- Stored, like every other result in this system.
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_tax numeric(14, 2),
    ADD COLUMN IF NOT EXISTS calc_equip_fuel numeric(14, 2);

COMMENT ON COLUMN mono_slabs.calc_tax IS
    'Sales tax on this pour''s materials + its share of taxable takeoff lines.';
COMMENT ON COLUMN mono_slabs.calc_equip_fuel IS
    'Fuel & maintenance uplift on this pour''s share of equipment rental days.';

ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS calc_total_tax numeric(14, 2);

INSERT INTO system_settings (key, value, description) VALUES
    ('sales_tax_pct', '0.0825'::jsonb,
     'Sales tax on materials. Skipped when the project is tax exempt.'),
    ('equip_fuel_maint_pct', '0.50'::jsonb,
     'Fuel & maintenance uplift on equipment rental day lines.'),
    ('labor_tie_steel_free_lb_per_sf', '0.35'::jsonb,
     'Rebar lb/SF carried before tie steel is paid. 0 bills all tonnage.')
ON CONFLICT (key) DO NOTHING;

-- ROW paving is always exempt, so give it a project type to be classified as.
-- (The API's type list is served from a literal; this is the data side.)

COMMIT;

-- After applying, rewrite the open estimates:
--   curl -s -X POST localhost:8001/api/system-settings/recalc-all
