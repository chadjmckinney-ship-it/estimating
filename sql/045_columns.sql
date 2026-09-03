-- 045_columns.sql
--
-- 07-COLUMNS: 68 cast-in-place columns in four types. 44,825.92 lb of steel,
-- 128.27 CY, 7,716 SF of form contact, $160,746.20 on the sheet.
--
-- Source: `07-COLUMNS` in the LBJ workbook, filled in by Chad on 2026-09-01 —
-- until then the tab was empty and columns was going to be the first assembly
-- built with no golden number. Every formula was read and reproduced to four
-- decimals against the sheet's own rows before any of this was written. The
-- full derivation is in `claude/columns-spec.md`.
--
-- ---------------------------------------------------------------------------
-- What one row is
-- ---------------------------------------------------------------------------
--
-- A column TYPE and how many of it there are — the fourth takeoff shape, after
-- the pour (mono_slabs, shared with paving), the group (pier_groups) and the
-- run (wall_runs). Closest to a pier group: a quantity of identical things,
-- measured in EA.
--
-- Three vertical bar sets per type, because the sheet carries three. Only the
-- first is used on LBJ; the other two exist so a column with a different bar
-- in the middle third can be entered without inventing a second type.
--
-- ---------------------------------------------------------------------------
-- Supervision is derived from a COUNT, on a five-day week
-- ---------------------------------------------------------------------------
--
-- The third duration model in the system, and both halves are new:
--
--     mono slab   SF / 16,000 per week   x 7 days
--     paving      SF / 25,000 per week   x 7 days
--     piers       typed, no derivation
--     COLUMNS     columns / 20 per week  x 5 days      <- this
--
-- 68 / 20 = 3.4 weeks, x 5 = 17 days. A column crew works a five-day week on
-- this sheet where every other assembly is billed seven, and the driver is a
-- count rather than an area. Both are stated as rates so neither is buried.

CREATE TABLE IF NOT EXISTS column_types (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections(id) ON DELETE CASCADE,

    label       text,
    description text,

    -- How many of this column. The section's unit is EA and this is what it
    -- counts; it also drives the supervision duration.
    qty         integer NOT NULL DEFAULT 0 CHECK (qty >= 0),

    mix_design_id integer REFERENCES mix_designs(id) ON DELETE SET NULL,

    -- ------------------------------------------------------------ geometry --
    height_ft   numeric(12, 3) NOT NULL DEFAULT 0,
    length_in   numeric(8, 3)  NOT NULL DEFAULT 0,
    width_in    numeric(8, 3)  NOT NULL DEFAULT 0,

    -- ------------------------------------------------------------ the cage --
    -- Three vertical sets. A set with no count or no size contributes nothing,
    -- rather than contributing a zero-weight bar.
    vert1_count integer,
    vert1_size  integer,
    vert2_count integer,
    vert2_size  integer,
    vert3_count integer,
    vert3_size  integer,

    tie_size        integer,
    tie_spacing_in  numeric(8, 3),

    dowel_count     integer,
    dowel_size      integer,
    dowel_length_ft numeric(8, 3),

    notes       text,
    sort_order  integer NOT NULL DEFAULT 0,

    -- ----------------------------------------------------------- quantities --
    -- Stored, not derived on read. Same rule as every other assembly: staleness
    -- is the dominant bug class here, so there is exactly one path that writes
    -- these (refresh_column_type_calcs) and everything else reads them.
    calc_form_sf          numeric(14, 4),   -- perimeter x height x qty
    calc_concrete_cy      numeric(14, 4),
    calc_vert_rebar_lb    numeric(14, 3),
    calc_tie_rebar_lb     numeric(14, 3),
    calc_dowel_rebar_lb   numeric(14, 3),
    calc_total_rebar_lb   numeric(14, 3),
    calc_chamfer_lf       numeric(14, 3),   -- 4 corners x height x qty

    -- ----------------------------------------------------------------- cost --
    calc_direct_cost    numeric(14, 2),
    calc_allocated_cost numeric(14, 2),
    calc_equip_fuel     numeric(14, 2),
    calc_tax            numeric(14, 2),
    calc_cost           numeric(14, 2),
    calc_sale           numeric(14, 2),
    calc_cost_per_unit  numeric(14, 4),     -- per COLUMN
    calc_sale_per_unit  numeric(14, 4),

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS column_types_section_idx ON column_types (section_id);

COMMENT ON TABLE column_types IS
    'One cast-in-place column type and its quantity (sql/045). Measured in EA; '
    'shared cost allocates by calc_form_sf, the way walls allocate by form feet.';

COMMENT ON COLUMN column_types.calc_form_sf IS
    'Contact area: (L + W) x 2 / 12 x height x qty. The sheet computes '
    'height x (L x W / 36) / 2 instead, which is a cross-section rather than a '
    'perimeter and runs 6-14% light depending on the column''s proportions. '
    'The sheet already holds the honest figure in its own column X ("Build '
    'up") and uses it for exactly one labor line.';

COMMENT ON COLUMN column_types.calc_chamfer_lf IS
    'Four corners x height x qty. The sheet''s S81 is SUM(height column) x 4, '
    'which never multiplies by quantity -- 240 LF on a 68-column job against '
    '4,368. Same class as the paving 2x4 bracing range.';


-- ---------------------------------------------------------------------------
-- Rates. NO PRICES -- see sql/044 and claude/design-decisions.md. Concrete,
-- steel, accessories, chamfer and cure all resolve through the catalog.
-- ---------------------------------------------------------------------------

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    -- Labor, all per SF of form contact except tie steel.
    ('columns', 'labor_build_up_sf',        0.50,  '07 D82'),
    ('columns', 'labor_forming_sf',         2.50,  '07 D83'),
    ('columns', 'labor_place_finish_sf',    1.25,  '07 D84'),
    ('columns', 'labor_wreck_sf',           0.50,  '07 D85'),
    ('columns', 'labor_rub_patch_sf',       0.25,  '07 D86'),
    ('columns', 'labor_tie_steel_ton',    450.00,  '07 D87 - every pound, as on piers'),

    -- Supervision from a COUNT, on a FIVE-day week. Both are firsts.
    ('columns', 'columns_per_super_week',  20.00,  '07 C92 = D54/20'),
    ('columns', 'labor_super_days_per_week', 5.00, '07 D92 = C92*5 - not 7'),
    ('columns', 'labor_super_sf_per_week',  0,     'columns derive from count, not area'),

    -- Waste and forming.
    ('columns', 'form_percent',             0.50,  '07 S67'),
    ('columns', 'waste_concrete',           0.04,  '07 J67'),
    ('columns', 'waste_rebar',              0.10,  '07 J72'),

    -- Nothing a column has.
    ('columns', 'support_rebar_lb_per_sf',  0,     'a column cage supports itself'),
    ('columns', 'vapor_barrier_enabled',    0,     'nothing goes under a column'),

    -- Lumber and consumable divisors read off the sheet''s own formulas.
    ('columns', 'lumber_2x4_per_sf',        1.00,  '07 S68 = face SF x form%'),
    ('columns', 'lumber_ply_per_sf',        0.0625,'07 S74 = face SF / 32 x 2 x form%'),
    ('columns', 'stakes_per_column',        0.02,  '07 S75 = ROUNDUP(columns / 2 / 25)'),
    ('columns', 'nails_16p_per_sf',      1800.00,  '07 S76 - one box per 1,800 SF'),
    ('columns', 'nails_8p_per_sf',       3000.00,  '07 S77 - 6p matches 8p'),
    ('columns', 'chamfer_per_column',       4.00,  '07 S81 - four corners'),
    ('columns', 'form_release_sf_per_gal', 300.00, '07 S105'),
    ('columns', 'chairs_sf_per_bag',    12000.00,  '07 S97'),

    -- Equipment day rates with no catalog item to carry them.
    ('columns', 'equip_storage_day_rate',  105.00, '07 F101'),
    ('columns', 'equip_misc_day_rate',      35.00, '07 F102'),

    -- Contract services.
    ('columns', 'concrete_pump_cy',         20.00, '07 F104'),
    ('columns', 'haul_off_cy',               6.00, '07 F108'),
    ('columns', 'out_of_town_day_rate',    200.00, '07 F109'),
    ('columns', 'saw_cutting_lf',            2.50, '07 F106'),
    ('columns', 'cure_sf',                   0.50, '07 F105')
ON CONFLICT (kind, key) DO NOTHING;
