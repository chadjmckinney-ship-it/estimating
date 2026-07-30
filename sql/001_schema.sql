-- Estimating System – initial schema (Mono Slab first)
-- Database: estimating
-- Apply: psql -d estimating -f sql/001_schema.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Reference: standard rebar weights (lb/ft)
-- ---------------------------------------------------------------------------
CREATE TABLE bar_weights (
    bar_size        smallint PRIMARY KEY CHECK (bar_size BETWEEN 3 AND 11),
    weight_lb_per_ft numeric(8, 4) NOT NULL,
    description     text GENERATED ALWAYS AS ('#' || bar_size::text) STORED
);

INSERT INTO bar_weights (bar_size, weight_lb_per_ft) VALUES
    (3,  0.376),
    (4,  0.668),
    (5,  1.043),
    (6,  1.502),
    (7,  2.044),
    (8,  2.670),
    (9,  3.400),
    (10, 4.303),
    (11, 5.313);

-- ---------------------------------------------------------------------------
-- Reference: mix designs (lookup; rates filled later)
-- ---------------------------------------------------------------------------
CREATE TABLE mix_designs (
    id          serial PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    description text,
    unit_cost   numeric(12, 4), -- $/CY when rate tables land
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO mix_designs (code, description) VALUES
    ('3000', '3000 psi'),
    ('3500', '3500 psi'),
    ('4000', '4000 psi'),
    ('4500', '4500 psi'),
    ('5000', '5000 psi');

-- ---------------------------------------------------------------------------
-- System settings / defaults (waste factors, PT rate, etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE system_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    description text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO system_settings (key, value, description) VALUES
    ('waste_concrete', '0.05'::jsonb, 'Default concrete waste factor (decimal, e.g. 0.05 = 5%) — TBD confirm'),
    ('waste_sand',     '0.05'::jsonb, 'Default sand waste factor — TBD confirm'),
    ('waste_rebar',    '0.00'::jsonb, 'Default rebar waste factor — TBD confirm'),
    ('pt_lb_per_sf',   '1.0'::jsonb,  'PT cable quantity: SF × this rate (lb/SF) — confirm with field'),
    ('support_rebar_lb_per_sf', '1.0'::jsonb, 'Slab support rebar: SF × this rate (lb/SF)');

-- ---------------------------------------------------------------------------
-- Users / estimators
-- ---------------------------------------------------------------------------
CREATE TABLE estimators (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username    text NOT NULL UNIQUE,
    full_name   text NOT NULL,
    email       text,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Projects & estimates
-- ---------------------------------------------------------------------------
CREATE TABLE projects (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    job_number  text,
    location    text,
    notes       text,
    created_by  uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE estimates (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    name             text NOT NULL,
    status           text NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft', 'in_review', 'final', 'archived')),
    estimator_id     uuid REFERENCES estimators (id) ON DELETE SET NULL,
    version          integer NOT NULL DEFAULT 1,
    -- Per-estimate waste overrides (NULL = use system_settings)
    waste_concrete   numeric(6, 4),
    waste_sand       numeric(6, 4),
    waste_rebar      numeric(6, 4),
    notes            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name, version)
);

CREATE INDEX estimates_project_id_idx ON estimates (project_id);

-- ---------------------------------------------------------------------------
-- Mono slab quantity inputs
-- ---------------------------------------------------------------------------
CREATE TABLE mono_slabs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id         uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    description         text,                    -- Description / Location
    location            text,
    square_footage      numeric(14, 3) NOT NULL CHECK (square_footage >= 0),
    thickness_in        numeric(8, 3)  NOT NULL CHECK (thickness_in > 0),
    post_tension        boolean NOT NULL DEFAULT false,
    mix_design_id       integer REFERENCES mix_designs (id) ON DELETE SET NULL,
    sand_thickness_in   numeric(8, 3) CHECK (sand_thickness_in IS NULL OR sand_thickness_in >= 0),
    perimeter_edge_lf   numeric(14, 3) CHECK (perimeter_edge_lf IS NULL OR perimeter_edge_lf >= 0),
    wire_mesh           boolean NOT NULL DEFAULT false,
    drops_ff            numeric(14, 3) CHECK (drops_ff IS NULL OR drops_ff >= 0),
    notes               text,
    sort_order          integer NOT NULL DEFAULT 0,
    -- Stored calculated quantities (refreshed by app / trigger later)
    calc_concrete_cy        numeric(14, 4),
    calc_sand_cy            numeric(14, 4),
    calc_support_rebar_lb   numeric(14, 3),
    calc_pt_cable_lb        numeric(14, 3),
    calc_grade_beam_rebar_lb numeric(14, 3),
    calc_total_rebar_lb     numeric(14, 3),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX mono_slabs_estimate_id_idx ON mono_slabs (estimate_id);

-- ---------------------------------------------------------------------------
-- Grade beams (one or more per mono slab)
-- ---------------------------------------------------------------------------
CREATE TABLE grade_beams (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mono_slab_id        uuid NOT NULL REFERENCES mono_slabs (id) ON DELETE CASCADE,
    label               text,
    width_in            numeric(8, 3)  NOT NULL CHECK (width_in > 0),
    height_in           numeric(8, 3)  NOT NULL CHECK (height_in > 0),
    length_lf           numeric(14, 3) NOT NULL CHECK (length_lf >= 0),
    -- Longitudinal bars: count + size (#)
    top_bars_count      integer CHECK (top_bars_count IS NULL OR top_bars_count >= 0),
    top_bars_size       smallint REFERENCES bar_weights (bar_size),
    bottom_bars_count   integer CHECK (bottom_bars_count IS NULL OR bottom_bars_count >= 0),
    bottom_bars_size    smallint REFERENCES bar_weights (bar_size),
    mid_bars_count      integer CHECK (mid_bars_count IS NULL OR mid_bars_count >= 0),
    mid_bars_size       smallint REFERENCES bar_weights (bar_size),
    -- Stirrups: size + spacing (inches)
    stirrup_size        smallint REFERENCES bar_weights (bar_size),
    stirrup_spacing_in  numeric(8, 3) CHECK (stirrup_spacing_in IS NULL OR stirrup_spacing_in > 0),
    -- L-bars optional: count + size + spacing
    l_bars_count        integer CHECK (l_bars_count IS NULL OR l_bars_count >= 0),
    l_bars_size         smallint REFERENCES bar_weights (bar_size),
    l_bars_spacing_in   numeric(8, 3) CHECK (l_bars_spacing_in IS NULL OR l_bars_spacing_in > 0),
    notes               text,
    sort_order          integer NOT NULL DEFAULT 0,
    calc_rebar_lb       numeric(14, 3),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX grade_beams_mono_slab_id_idx ON grade_beams (mono_slab_id);

-- ---------------------------------------------------------------------------
-- Supplier bid comparison
-- ---------------------------------------------------------------------------
CREATE TABLE supplier_bids (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id             uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    supplier_name           text NOT NULL,
    quoted_rebar_weight_lb  numeric(14, 3),
    quoted_rebar_price      numeric(14, 2),
    quoted_pt_qty           numeric(14, 3),
    quoted_pt_price         numeric(14, 2),
    bid_date                date,
    notes                   text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX supplier_bids_estimate_id_idx ON supplier_bids (estimate_id);

-- Variance view: calculated totals vs each supplier quote
CREATE OR REPLACE VIEW supplier_bid_variance AS
SELECT
    sb.id AS bid_id,
    sb.estimate_id,
    sb.supplier_name,
    calc.total_rebar_lb   AS calc_rebar_lb,
    sb.quoted_rebar_weight_lb,
    CASE
        WHEN sb.quoted_rebar_weight_lb IS NULL OR calc.total_rebar_lb IS NULL THEN NULL
        ELSE sb.quoted_rebar_weight_lb - calc.total_rebar_lb
    END AS rebar_variance_lb,
    CASE
        WHEN sb.quoted_rebar_weight_lb IS NULL OR calc.total_rebar_lb IS NULL OR calc.total_rebar_lb = 0 THEN NULL
        ELSE round(
            ((sb.quoted_rebar_weight_lb - calc.total_rebar_lb) / calc.total_rebar_lb) * 100,
            2
        )
    END AS rebar_variance_pct,
    calc.total_pt_lb      AS calc_pt_lb,
    sb.quoted_pt_qty,
    CASE
        WHEN sb.quoted_pt_qty IS NULL OR calc.total_pt_lb IS NULL THEN NULL
        ELSE sb.quoted_pt_qty - calc.total_pt_lb
    END AS pt_variance,
    sb.quoted_rebar_price,
    sb.quoted_pt_price,
    sb.bid_date
FROM supplier_bids sb
LEFT JOIN LATERAL (
    SELECT
        coalesce(sum(ms.calc_total_rebar_lb), 0) AS total_rebar_lb,
        coalesce(sum(ms.calc_pt_cable_lb), 0)    AS total_pt_lb
    FROM mono_slabs ms
    WHERE ms.estimate_id = sb.estimate_id
) calc ON true;

-- ---------------------------------------------------------------------------
-- eTakeoff CSV import audit
-- ---------------------------------------------------------------------------
CREATE TABLE etakeoff_imports (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     uuid REFERENCES estimates (id) ON DELETE SET NULL,
    filename        text NOT NULL,
    imported_by     uuid REFERENCES estimators (id) ON DELETE SET NULL,
    imported_at     timestamptz NOT NULL DEFAULT now(),
    row_count       integer,
    column_map      jsonb,   -- eTakeoff column → system field mapping
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'mapped', 'applied', 'failed')),
    error_message   text,
    raw_preview     jsonb    -- first N rows for mapping UI
);

-- ---------------------------------------------------------------------------
-- Helper functions: locked calculation logic (PT SOG)
-- waste is decimal e.g. 0.05
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION calc_concrete_cy(
    sf numeric,
    thickness_in numeric,
    waste numeric DEFAULT 0
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT round((sf * thickness_in / 12.0 / 27.0) * (1 + coalesce(waste, 0)), 4);
$$;

CREATE OR REPLACE FUNCTION calc_sand_cy(
    sf numeric,
    sand_thickness_in numeric,
    waste numeric DEFAULT 0
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN sand_thickness_in IS NULL THEN NULL
        ELSE round((sf * sand_thickness_in / 12.0 / 27.0) * (1 + coalesce(waste, 0)), 4)
    END;
$$;

CREATE OR REPLACE FUNCTION calc_support_rebar_lb(
    sf numeric,
    lb_per_sf numeric DEFAULT 1.0
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT round(sf * coalesce(lb_per_sf, 1.0), 3);
$$;

CREATE OR REPLACE FUNCTION calc_pt_cable_lb(
    sf numeric,
    post_tension boolean,
    lb_per_sf numeric DEFAULT 1.0
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN coalesce(post_tension, false)
            THEN round(sf * coalesce(lb_per_sf, 1.0), 3)
        ELSE 0
    END;
$$;

-- Longitudinal bar weight for a grade beam run (count × length × lb/ft)
CREATE OR REPLACE FUNCTION calc_long_bar_lb(
    bar_count integer,
    bar_size smallint,
    length_lf numeric
) RETURNS numeric
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN bar_count IS NULL OR bar_size IS NULL OR length_lf IS NULL THEN 0
        ELSE round(
            bar_count * length_lf * (
                SELECT weight_lb_per_ft FROM bar_weights WHERE bar_weights.bar_size = calc_long_bar_lb.bar_size
            ),
            3
        )
    END;
$$;

-- Stirrup estimate: perimeter of cross-section + hooks allowance, × count
-- Count ≈ length_lf * 12 / spacing_in
-- Perimeter ≈ 2*(width + height) in feet; + 2*3" hooks ≈ +0.5 ft (simple default)
CREATE OR REPLACE FUNCTION calc_stirrup_lb(
    width_in numeric,
    height_in numeric,
    length_lf numeric,
    stirrup_size smallint,
    spacing_in numeric
) RETURNS numeric
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN stirrup_size IS NULL OR spacing_in IS NULL OR spacing_in <= 0 THEN 0
        ELSE round(
            (length_lf * 12.0 / spacing_in)
            * ((2.0 * (width_in + height_in) / 12.0) + 0.5)
            * (SELECT weight_lb_per_ft FROM bar_weights WHERE bar_weights.bar_size = calc_stirrup_lb.stirrup_size),
            3
        )
    END;
$$;

COMMENT ON TABLE mono_slabs IS 'Main slab quantity inputs for Mono Slab / PT SOG estimates';
COMMENT ON TABLE grade_beams IS 'Grade beam bar schedule; rebar weight derived from bar_weights';
COMMENT ON FUNCTION calc_concrete_cy IS '(SF × Thickness_in / 12 / 27) × (1 + waste)';
COMMENT ON FUNCTION calc_sand_cy IS '(SF × Sand_Thickness_in / 12 / 27) × (1 + waste)';
COMMENT ON FUNCTION calc_support_rebar_lb IS 'SF × support_rebar_lb_per_sf (default 1.0)';
COMMENT ON FUNCTION calc_pt_cable_lb IS 'SF × pt_lb_per_sf when post_tension; else 0';

COMMIT;
