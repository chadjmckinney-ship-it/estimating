-- Slab bar mat: real rebar takeoff from bar size + spacing, replacing the flat
-- lb/SF stand-in as the primary slab steel quantity.
--
-- Plans call the mat out as e.g. #4 @ 18" O.C.E.W. Steel runs both directions at
-- that spacing, so:
--     LF = 2 × SF × 12 / spacing_in          (12/spacing = LF of bar per ft of run)
--     lb = LF × weight_lb_per_ft(size) × (1 + waste_rebar)
--
-- waste_rebar (previously stored but used by no calc) now carries the lap-splice
-- allowance for the mat. It is NOT applied to grade-beam or support steel, so no
-- existing beam quantity moves.
--
-- support_rebar_lb_per_sf keeps its name and its flat SF × rate formula, but now
-- means only what the name says — chairs, dowels, misc support — so its system
-- default drops 1.0 → 0.1 lb/SF. Pours that left it blank will fall from
-- SF × 1.0 to SF × 0.1; pours with an explicit override are unaffected.
--
-- Slab rebar = mat + support. Total rebar = mat + support + (GB + Exp + Drop).
--
-- Apply: psql -d estimating -f sql/021_slab_bar_mat.sql

BEGIN;

-- ---------------------------------------------------------------- inputs ----

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS slab_bar_size       smallint,
    ADD COLUMN IF NOT EXISTS slab_bar_spacing_in numeric(8, 3);

ALTER TABLE mono_slabs
    DROP CONSTRAINT IF EXISTS mono_slabs_slab_bar_size_check;
ALTER TABLE mono_slabs
    ADD CONSTRAINT mono_slabs_slab_bar_size_check
    CHECK (slab_bar_size IS NULL OR (slab_bar_size >= 3 AND slab_bar_size <= 11));

ALTER TABLE mono_slabs
    DROP CONSTRAINT IF EXISTS mono_slabs_slab_bar_spacing_check;
ALTER TABLE mono_slabs
    ADD CONSTRAINT mono_slabs_slab_bar_spacing_check
    CHECK (slab_bar_spacing_in IS NULL OR slab_bar_spacing_in > 0);

COMMENT ON COLUMN mono_slabs.slab_bar_size IS
    'Slab mat bar size #3-#11 (e.g. 4 for #4). NULL = no mat priced on this pour.';
COMMENT ON COLUMN mono_slabs.slab_bar_spacing_in IS
    'Slab mat spacing inches o.c., each way. NULL = no mat priced on this pour.';

-- --------------------------------------------------------------- outputs ----

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_slab_bar_lf numeric(14, 3),
    ADD COLUMN IF NOT EXISTS calc_slab_bar_lb numeric(14, 3);

COMMENT ON COLUMN mono_slabs.calc_slab_bar_lf IS
    'Slab mat bar length: 2 × SF × 12 / spacing (each way).';
COMMENT ON COLUMN mono_slabs.calc_slab_bar_lb IS
    'Slab mat weight: LF × lb/ft × (1 + waste_rebar). Excludes support rebar.';

-- ------------------------------------------------------- locked functions ----

CREATE OR REPLACE FUNCTION calc_slab_mat_rebar_lf(
    sf         numeric,
    spacing_in numeric
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN sf IS NULL OR sf <= 0 THEN 0
        WHEN spacing_in IS NULL OR spacing_in <= 0 THEN 0
        -- 12 / spacing = bars per foot of run; × SF = LF one way; × 2 = each way
        ELSE round(2 * sf * 12.0 / spacing_in, 3)
    END;
$$;

COMMENT ON FUNCTION calc_slab_mat_rebar_lf IS
    'Slab mat bar LF, each way: 2 × SF × 12 / spacing_in';

CREATE OR REPLACE FUNCTION calc_slab_mat_rebar_lb(
    sf         numeric,
    bar_size   smallint,
    spacing_in numeric,
    waste      numeric DEFAULT 0
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN bar_size IS NULL OR spacing_in IS NULL OR spacing_in <= 0 THEN 0
        WHEN sf IS NULL OR sf <= 0 THEN 0
        ELSE round(
            calc_slab_mat_rebar_lf(sf, spacing_in)
            * coalesce((
                SELECT weight_lb_per_ft FROM bar_weights
                WHERE bar_weights.bar_size = calc_slab_mat_rebar_lb.bar_size
            ), 0)
            * (1 + coalesce(waste, 0)),
            3
        )
    END;
$$;

COMMENT ON FUNCTION calc_slab_mat_rebar_lb IS
    'Slab mat weight: (2 × SF × 12 / spacing) × lb/ft(size) × (1 + waste). '
    'Waste carries the lap-splice allowance (estimates.waste_rebar).';

-- ------------------------------------------------- support rebar re-basing ----

-- The mat is now priced explicitly, so this line means only chairs / dowels /
-- misc support steel. 1.0 lb/SF was standing in for the whole mat.
UPDATE system_settings
SET value = '0.1'::jsonb
WHERE key = 'support_rebar_lb_per_sf';

COMMENT ON COLUMN mono_slabs.support_rebar_lb_per_sf IS
    'Support steel only (chairs, dowels, misc) lb/SF; NULL = system default 0.1. '
    'The main mat is priced from slab_bar_size + slab_bar_spacing_in.';

COMMIT;
