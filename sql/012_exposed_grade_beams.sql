-- OBSOLETE: estimate-level exposed GBs (wrong model).
-- Replaced by sql/013_grade_beam_kinds.sql — exposed/drops are per mono_slab pour
-- (Excel 04 EXP GB / Drops), same table as grade_beams with kind column.
-- Do not re-apply this migration on new installs; use 013 only if rebuilding.

-- Original intent (kept for history):
-- Exposed grade beams: poured separately from SOG (Excel 02-Gd Beams)
-- Parent = estimate, NOT mono_slab
-- Apply: psql -d estimating -f sql/012_exposed_grade_beams.sql

BEGIN;

CREATE TABLE IF NOT EXISTS exposed_grade_beams (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id         uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    label               text,                          -- GB type / description
    mix_design_id       integer REFERENCES mix_designs (id) ON DELETE SET NULL,
    length_lf           numeric(14, 3) NOT NULL CHECK (length_lf >= 0),
    width_in            numeric(8, 3) NOT NULL CHECK (width_in > 0),
    height_in           numeric(8, 3) NOT NULL CHECK (height_in > 0),
    top_bars_count      integer CHECK (top_bars_count IS NULL OR top_bars_count >= 0),
    top_bars_size       smallint REFERENCES bar_weights (bar_size),
    bottom_bars_count   integer CHECK (bottom_bars_count IS NULL OR bottom_bars_count >= 0),
    bottom_bars_size    smallint REFERENCES bar_weights (bar_size),
    mid_bars_count      integer CHECK (mid_bars_count IS NULL OR mid_bars_count >= 0),
    mid_bars_size       smallint REFERENCES bar_weights (bar_size),
    stirrup_size        smallint REFERENCES bar_weights (bar_size),
    stirrup_spacing_in  numeric(8, 3) CHECK (stirrup_spacing_in IS NULL OR stirrup_spacing_in > 0),
    l_bars_count        integer CHECK (l_bars_count IS NULL OR l_bars_count >= 0),
    l_bars_size         smallint REFERENCES bar_weights (bar_size),
    l_bars_spacing_in   numeric(8, 3) CHECK (l_bars_spacing_in IS NULL OR l_bars_spacing_in > 0),
    notes               text,
    sort_order          integer NOT NULL DEFAULT 0,
    calc_rebar_lb       numeric(14, 3),
    calc_concrete_cy    numeric(14, 4),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS exposed_grade_beams_estimate_id_idx
    ON exposed_grade_beams (estimate_id);

COMMENT ON TABLE exposed_grade_beams IS
    'Grade beams poured separately from mono slab (Excel 02-Gd Beams); per estimate';
COMMENT ON COLUMN exposed_grade_beams.calc_concrete_cy IS
    '(W_in × H_in × L_ft) / (144×27) × (1+waste)';
COMMENT ON COLUMN exposed_grade_beams.calc_rebar_lb IS
    'From bar schedule using bar_weights + stirrup formula';

COMMIT;
