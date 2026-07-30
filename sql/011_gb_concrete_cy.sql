-- Grade beam concrete CY + pour rollup (slab CY + GB CY)
-- GB CY = (width_in × height_in × length_lf) / (144 × 27) × (1 + waste)
-- Apply: psql -d estimating -f sql/011_gb_concrete_cy.sql

BEGIN;

ALTER TABLE grade_beams
    ADD COLUMN IF NOT EXISTS calc_concrete_cy numeric(14, 4);

COMMENT ON COLUMN grade_beams.calc_concrete_cy IS
    'Concrete CY for this GB: (W_in × H_in × L_ft) / (144×27) × (1+waste)';

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_slab_concrete_cy numeric(14, 4),
    ADD COLUMN IF NOT EXISTS calc_gb_concrete_cy numeric(14, 4);

COMMENT ON COLUMN mono_slabs.calc_slab_concrete_cy IS 'SOG slab concrete CY only (no grade beams)';
COMMENT ON COLUMN mono_slabs.calc_gb_concrete_cy IS 'Sum of grade beam concrete CY on this pour';
COMMENT ON COLUMN mono_slabs.calc_concrete_cy IS
    'Total pour concrete CY = slab + grade beams';

-- Backfill: previous calc_concrete_cy was slab-only
UPDATE mono_slabs
SET calc_slab_concrete_cy = calc_concrete_cy
WHERE calc_slab_concrete_cy IS NULL AND calc_concrete_cy IS NOT NULL;

UPDATE mono_slabs
SET calc_gb_concrete_cy = 0
WHERE calc_gb_concrete_cy IS NULL;

COMMIT;
