-- Per-pour SOG support rebar & PT rate overrides (lb/SF)
-- NULL = use system_settings (support_rebar_lb_per_sf, pt_lb_per_sf)
-- Apply: psql -d estimating -f sql/009_mono_slab_rebar_pt_rates.sql

BEGIN;

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS support_rebar_lb_per_sf numeric(8, 4)
        CHECK (support_rebar_lb_per_sf IS NULL OR support_rebar_lb_per_sf >= 0),
    ADD COLUMN IF NOT EXISTS pt_lb_per_sf numeric(8, 4)
        CHECK (pt_lb_per_sf IS NULL OR pt_lb_per_sf >= 0);

COMMENT ON COLUMN mono_slabs.support_rebar_lb_per_sf IS
    'SOG support rebar rate lb/SF; NULL uses system_settings.support_rebar_lb_per_sf';
COMMENT ON COLUMN mono_slabs.pt_lb_per_sf IS
    'PT cable rate lb/SF when post_tension; NULL uses system_settings.pt_lb_per_sf';

COMMIT;
