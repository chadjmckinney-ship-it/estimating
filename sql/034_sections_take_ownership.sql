-- 034: sections take ownership; estimates become the rollup
--
-- sql/033 created estimate_sections and populated section_id on every child
-- table while leaving estimate_id in place, so the running app kept working.
-- This finishes the move: section_id becomes the only parent.
--
-- Two parents on one row is the stored-not-derived bug this codebase keeps
-- finding — the same shape as the calc_* columns that go stale, or the vapor
-- barrier matched by name in two places. So estimate_id goes rather than
-- lingering as a convenience: an estimate reaches its work through its
-- sections, and nothing else.
--
-- The three *_summary tables are pure caches of the line tables, rewritten on
-- every refresh, so they are simply re-created on the new key.
--
-- Settings that describe an assembly (form_percent, the wastes, the vapor
-- barrier and tape) moved onto the section in 033 and are dropped from
-- estimates here. Markup does NOT: estimates keep margin_pct and
-- contingency_pct as the default a new section is created with, while each
-- section carries the markup it is actually priced at.
--
-- Acceptance: LBJ still totals $671,712.74. Apply sql/033 first.

BEGIN;

-- ---------------------------------------------------------------------------
-- Guard: refuse to run if 033 did not fully land
-- ---------------------------------------------------------------------------

DO $$
DECLARE orphans integer;
BEGIN
    SELECT
        (SELECT count(*) FROM mono_slabs WHERE section_id IS NULL)
      + (SELECT count(*) FROM estimate_forming_lines WHERE section_id IS NULL)
      + (SELECT count(*) FROM estimate_labor_lines WHERE section_id IS NULL)
      + (SELECT count(*) FROM estimate_equipment_lines WHERE section_id IS NULL)
      + (SELECT count(*) FROM estimate_beam_types WHERE section_id IS NULL)
    INTO orphans;

    IF orphans > 0 THEN
        RAISE EXCEPTION
            'sql/033 has not fully populated section_id (% orphan rows). '
            'Run 033 and check `dbquery.py --check orphans` before 034.', orphans;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- section_id becomes required, and the only parent
-- ---------------------------------------------------------------------------

ALTER TABLE mono_slabs               ALTER COLUMN section_id SET NOT NULL;
ALTER TABLE estimate_forming_lines   ALTER COLUMN section_id SET NOT NULL;
ALTER TABLE estimate_labor_lines     ALTER COLUMN section_id SET NOT NULL;
ALTER TABLE estimate_equipment_lines ALTER COLUMN section_id SET NOT NULL;
ALTER TABLE estimate_beam_types      ALTER COLUMN section_id SET NOT NULL;

-- Uniqueness follows the parent: one line per code per SECTION, so a job can
-- carry a FORMING line on its slab section and another on its paving section.
ALTER TABLE estimate_forming_lines   DROP CONSTRAINT IF EXISTS estimate_forming_lines_estimate_id_code_key;
ALTER TABLE estimate_labor_lines     DROP CONSTRAINT IF EXISTS estimate_labor_lines_estimate_id_code_key;
ALTER TABLE estimate_equipment_lines DROP CONSTRAINT IF EXISTS estimate_equipment_lines_estimate_id_code_key;

ALTER TABLE estimate_forming_lines   ADD CONSTRAINT estimate_forming_lines_section_code_key   UNIQUE (section_id, code);
ALTER TABLE estimate_labor_lines     ADD CONSTRAINT estimate_labor_lines_section_code_key     UNIQUE (section_id, code);
ALTER TABLE estimate_equipment_lines ADD CONSTRAINT estimate_equipment_lines_section_code_key UNIQUE (section_id, code);

DROP INDEX IF EXISTS estimate_beam_types_estimate_label_idx;
CREATE UNIQUE INDEX IF NOT EXISTS estimate_beam_types_section_label_idx
    ON estimate_beam_types (section_id, label);

-- The view exposed t.estimate_id; the beam type now belongs to a section.
-- Dropped and recreated rather than replaced: CREATE OR REPLACE VIEW cannot
-- change a column, only add to the end.
DROP VIEW IF EXISTS grade_beam_details;
CREATE VIEW grade_beam_details AS
SELECT
    gb.id, gb.mono_slab_id, gb.beam_type_id, gb.length_lf, gb.notes,
    gb.sort_order, gb.created_at, gb.updated_at,
    gb.calc_rebar_lb, gb.calc_pt_cable_lf, gb.calc_concrete_cy, gb.calc_poly_sf,
    t.section_id, t.label, t.kind, t.width_in, t.height_in,
    -- form_face_in arrived with the brick ledge in sql/028; a view rebuilt from
    -- the 025 column list would silently drop it.
    t.form_face_in,
    t.top_bars_count, t.top_bars_size, t.bottom_bars_count, t.bottom_bars_size,
    t.mid_bars_count, t.mid_bars_size, t.stirrup_size, t.stirrup_spacing_in,
    t.l_bars_count, t.l_bars_size, t.l_bars_spacing_in, t.pt_cables_count
FROM grade_beams gb
JOIN estimate_beam_types t ON t.id = gb.beam_type_id;

COMMENT ON VIEW grade_beam_details IS
    'grade_beams joined to its estimate_beam_types row, keyed by section (034).';

-- supplier_bid_variance reached the pours by mono_slabs.estimate_id. A pour now
-- reaches its job through its section, so the lateral joins one level deeper.
-- A supplier bid is still a job-level thing: it is quoted against the whole
-- estimate, so it sums the pours of every section.
DROP VIEW IF EXISTS supplier_bid_variance;
CREATE VIEW supplier_bid_variance AS
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
    JOIN estimate_sections s ON s.id = ms.section_id
    WHERE s.estimate_id = sb.estimate_id
) calc ON true;

DROP INDEX IF EXISTS mono_slabs_estimate_id_idx;
DROP INDEX IF EXISTS estimate_forming_lines_estimate_id_idx;
DROP INDEX IF EXISTS estimate_labor_lines_estimate_id_idx;
DROP INDEX IF EXISTS estimate_equipment_lines_estimate_id_idx;
DROP INDEX IF EXISTS estimate_beam_types_estimate_idx;

ALTER TABLE mono_slabs               DROP COLUMN IF EXISTS estimate_id;
ALTER TABLE estimate_forming_lines   DROP COLUMN IF EXISTS estimate_id;
ALTER TABLE estimate_labor_lines     DROP COLUMN IF EXISTS estimate_id;
ALTER TABLE estimate_equipment_lines DROP COLUMN IF EXISTS estimate_id;
ALTER TABLE estimate_beam_types      DROP COLUMN IF EXISTS estimate_id;

-- ---------------------------------------------------------------------------
-- Summary caches, re-keyed. Nothing to preserve — a refresh rewrites them.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS estimate_forming_summary;
CREATE TABLE estimate_forming_summary (
    section_id      uuid PRIMARY KEY REFERENCES estimate_sections (id) ON DELETE CASCADE,
    pour_count      integer NOT NULL DEFAULT 0,
    total_sf        numeric(14, 3) NOT NULL DEFAULT 0,
    perimeter_lf    numeric(14, 3) NOT NULL DEFAULT 0,
    drops_ff        numeric(14, 3) NOT NULL DEFAULT 0,
    mesh_sf         numeric(14, 3) NOT NULL DEFAULT 0,
    total_rebar_lb  numeric(14, 3) NOT NULL DEFAULT 0,
    form_percent    numeric(8, 4) NOT NULL DEFAULT 0.50,
    form_waste      numeric(8, 4) NOT NULL DEFAULT 0,
    total_ext_cost  numeric(14, 2) NOT NULL DEFAULT 0,
    refreshed_at    timestamptz NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS estimate_labor_summary;
CREATE TABLE estimate_labor_summary (
    section_id          uuid PRIMARY KEY REFERENCES estimate_sections (id) ON DELETE CASCADE,
    pour_count          integer NOT NULL DEFAULT 0,
    total_sf            numeric(14, 3) NOT NULL DEFAULT 0,
    drops_ff            numeric(14, 3) NOT NULL DEFAULT 0,
    total_rebar_lb      numeric(14, 3) NOT NULL DEFAULT 0,
    total_rebar_tons    numeric(14, 4) NOT NULL DEFAULT 0,
    super_weeks         numeric(12, 4) NOT NULL DEFAULT 0,
    super_days          numeric(12, 4) NOT NULL DEFAULT 0,
    total_labor_cost    numeric(14, 2) NOT NULL DEFAULT 0,
    total_supervision_cost numeric(14, 2) NOT NULL DEFAULT 0,
    total_cost          numeric(14, 2) NOT NULL DEFAULT 0,
    cost_per_sf         numeric(12, 4),
    refreshed_at        timestamptz NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS estimate_equipment_summary;
CREATE TABLE estimate_equipment_summary (
    section_id          uuid PRIMARY KEY REFERENCES estimate_sections (id) ON DELETE CASCADE,
    pour_count          integer NOT NULL DEFAULT 0,
    total_sf            numeric(14, 3) NOT NULL DEFAULT 0,
    super_days          numeric(12, 4) NOT NULL DEFAULT 0,
    equip_days          numeric(12, 4) NOT NULL DEFAULT 0,
    total_concrete_cy   numeric(14, 4) NOT NULL DEFAULT 0,
    total_equipment_cost numeric(14, 2) NOT NULL DEFAULT 0,
    total_contract_cost numeric(14, 2) NOT NULL DEFAULT 0,
    total_cost          numeric(14, 2) NOT NULL DEFAULT 0,
    cost_per_sf         numeric(12, 4),
    refreshed_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Assembly settings now live on the section
-- ---------------------------------------------------------------------------

ALTER TABLE estimates DROP COLUMN IF EXISTS form_percent;
ALTER TABLE estimates DROP COLUMN IF EXISTS waste_concrete;
ALTER TABLE estimates DROP COLUMN IF EXISTS waste_sand;
ALTER TABLE estimates DROP COLUMN IF EXISTS waste_rebar;
ALTER TABLE estimates DROP COLUMN IF EXISTS vapor_barrier_material_id;
ALTER TABLE estimates DROP COLUMN IF EXISTS vapor_tape_material_id;

COMMENT ON COLUMN estimates.margin_pct IS
    'Default margin for new sections. The priced markup lives on each section.';
COMMENT ON COLUMN estimates.contingency_pct IS
    'Default contingency for new sections.';
COMMENT ON TABLE estimates IS
    'A job. Owns tax treatment, markup defaults and the rollup; the work lives '
    'in estimate_sections.';

COMMIT;
