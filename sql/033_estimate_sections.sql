-- 033: an estimate becomes a job; its assemblies become sections
--
-- Until now an estimate WAS a mono-slab worksheet: mono_slabs, forming, labor,
-- equipment and beam types all hang directly off estimates, and the estimate
-- page is the mono-slab page. That mirrors one tab of the workbook, not a job.
--
-- A real job is the workbook's Summary tab. LBJ is $1,388,113 across three
-- filled sections (01-PIERS 106 EA, 04-PT SLABS 62,723 SF, 06-WALLS 3,452 FF);
-- the sheet reconciled so far is one of them. Each sheet carries its own labor
-- rates, supervision, equipment and takeoff, and its own quantity AND unit.
-- Paving's forming labor is $0.30/SF against the slab sheet's $0.45, its steel
-- $0.55/lb against $0.60. Adding paving under the current shape would have
-- priced it at slab rates with no error shown.
--
-- So: estimates keep the job-level facts and roll up; sections own the work.
--
--   projects → estimates (the job) → estimate_sections (the assemblies)
--
-- This migration is DATA-SAFE and CODE-COMPATIBLE. It creates the table, gives
-- every existing estimate exactly one 'mono_slab' section carrying its current
-- settings, and adds a populated section_id to each child table. It does NOT
-- drop estimate_id from those tables, so nothing in the app breaks on apply.
-- Re-pointing the services and dropping the old column is sql/034.
--
-- Acceptance: no total changes. LBJ must still read $671,712.74.

BEGIN;

-- ---------------------------------------------------------------------------
-- The sections
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS estimate_sections (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id   uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    kind          text NOT NULL,
    name          text NOT NULL,
    -- The unit the assembly is measured in — EA for piers, SF for slabs and
    -- paving, FF for walls, LS for miscellaneous. A property of the assembly,
    -- not the job, which is why it lives here.
    unit          text NOT NULL DEFAULT 'SF',
    sort_order    integer NOT NULL DEFAULT 0,

    -- Markup is per section, defaulting to 20% and adjusted per section.
    margin_pct        numeric(6, 4) NOT NULL DEFAULT 0.20,
    contingency_pct   numeric(6, 4) NOT NULL DEFAULT 0.00,

    -- Tax exemption is a PROJECT fact with a SECTION exception: ROW paving and
    -- sidewalks are exempt inside jobs that are otherwise taxable. NULL means
    -- inherit projects.tax_exempt; true/false overrides it for this section.
    -- Deliberately not defaulted by kind — plenty of paving is not ROW, and
    -- silently exempting it would be a wrong number with no error.
    tax_exempt    boolean,

    -- Settings that describe the assembly, moved off estimates.
    form_percent              numeric(6, 4),
    waste_concrete            numeric(6, 4),
    waste_sand                numeric(6, 4),
    waste_rebar               numeric(6, 4),
    vapor_barrier_material_id integer REFERENCES materials (id) ON DELETE SET NULL,
    vapor_tape_material_id    integer REFERENCES materials (id) ON DELETE SET NULL,

    -- Rollup, same shape as the estimate's
    calc_total_cost   numeric(14, 2),
    calc_total_tax    numeric(14, 2),
    calc_total_sale   numeric(14, 2),
    calc_quantity     numeric(14, 3),
    calc_cost_per_unit numeric(12, 4),
    calc_sale_per_unit numeric(12, 4),

    notes         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT estimate_sections_kind_check CHECK (kind IN (
        'mono_slab', 'paving', 'sidewalk', 'piers', 'grade_beams',
        'walls_footings', 'columns', 'slabs', 'cip_deck', 'slab_on_deck',
        'panels', 'miscellaneous'
    ))
);

CREATE INDEX IF NOT EXISTS estimate_sections_estimate_id_idx
    ON estimate_sections (estimate_id);

COMMENT ON TABLE estimate_sections IS
    'One assembly of a job — the workbook''s per-sheet level. Owns its own '
    'rates, takeoff, markup and (optionally) tax treatment.';
COMMENT ON COLUMN estimate_sections.tax_exempt IS
    'NULL = inherit projects.tax_exempt. Set only where the section differs — '
    'ROW paving and sidewalks inside an otherwise taxable job.';

-- ---------------------------------------------------------------------------
-- One section per existing estimate, carrying that estimate's settings
-- ---------------------------------------------------------------------------

INSERT INTO estimate_sections (
    estimate_id, kind, name, unit, sort_order,
    margin_pct, contingency_pct,
    form_percent, waste_concrete, waste_sand, waste_rebar,
    vapor_barrier_material_id, vapor_tape_material_id
)
SELECT
    e.id, 'mono_slab', 'Mono slab on grade', 'SF', 10,
    -- Carried across, NOT reset to the new 20% default: an existing estimate
    -- must not change price because the furniture moved. LBJ is at 0.15/0.00
    -- to match the bid it was won at.
    e.margin_pct, e.contingency_pct,
    e.form_percent, e.waste_concrete, e.waste_sand, e.waste_rebar,
    e.vapor_barrier_material_id, e.vapor_tape_material_id
FROM estimates e
WHERE NOT EXISTS (
    SELECT 1 FROM estimate_sections s WHERE s.estimate_id = e.id
);

-- ---------------------------------------------------------------------------
-- Point the children at their section (populated; estimate_id stays for now)
-- ---------------------------------------------------------------------------

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS section_id uuid
    REFERENCES estimate_sections (id) ON DELETE CASCADE;
ALTER TABLE estimate_forming_lines
    ADD COLUMN IF NOT EXISTS section_id uuid
    REFERENCES estimate_sections (id) ON DELETE CASCADE;
ALTER TABLE estimate_labor_lines
    ADD COLUMN IF NOT EXISTS section_id uuid
    REFERENCES estimate_sections (id) ON DELETE CASCADE;
ALTER TABLE estimate_equipment_lines
    ADD COLUMN IF NOT EXISTS section_id uuid
    REFERENCES estimate_sections (id) ON DELETE CASCADE;
ALTER TABLE estimate_beam_types
    ADD COLUMN IF NOT EXISTS section_id uuid
    REFERENCES estimate_sections (id) ON DELETE CASCADE;

UPDATE mono_slabs c SET section_id = s.id
    FROM estimate_sections s WHERE s.estimate_id = c.estimate_id AND c.section_id IS NULL;
UPDATE estimate_forming_lines c SET section_id = s.id
    FROM estimate_sections s WHERE s.estimate_id = c.estimate_id AND c.section_id IS NULL;
UPDATE estimate_labor_lines c SET section_id = s.id
    FROM estimate_sections s WHERE s.estimate_id = c.estimate_id AND c.section_id IS NULL;
UPDATE estimate_equipment_lines c SET section_id = s.id
    FROM estimate_sections s WHERE s.estimate_id = c.estimate_id AND c.section_id IS NULL;
UPDATE estimate_beam_types c SET section_id = s.id
    FROM estimate_sections s WHERE s.estimate_id = c.estimate_id AND c.section_id IS NULL;

CREATE INDEX IF NOT EXISTS mono_slabs_section_id_idx ON mono_slabs (section_id);
CREATE INDEX IF NOT EXISTS estimate_forming_lines_section_id_idx ON estimate_forming_lines (section_id);
CREATE INDEX IF NOT EXISTS estimate_labor_lines_section_id_idx ON estimate_labor_lines (section_id);
CREATE INDEX IF NOT EXISTS estimate_equipment_lines_section_id_idx ON estimate_equipment_lines (section_id);
CREATE INDEX IF NOT EXISTS estimate_beam_types_section_id_idx ON estimate_beam_types (section_id);

-- The per-estimate summary tables are keyed by estimate_id as their PK, so they
-- are re-keyed in sql/034 alongside the service change that writes them. They
-- are pure caches of the line tables and are rewritten on every refresh, so
-- there is nothing to preserve.

COMMIT;

-- Verify before going further:
--   SELECT e.name, count(s.id) FROM estimates e
--   LEFT JOIN estimate_sections s ON s.estimate_id = e.id GROUP BY e.name;
--     → exactly one section per estimate
--   SELECT count(*) FROM mono_slabs WHERE section_id IS NULL;   → 0
--   SELECT count(*) FROM estimate_beam_types WHERE section_id IS NULL; → 0
-- and the LBJ estimate must still total 671712.74.
