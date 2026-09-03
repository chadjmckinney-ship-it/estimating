-- 040_walls.sql
--
-- 06-Walls & Footings: 652 LF of retaining wall on continuous footing.
-- 3,452.55 form feet, 33,727.83 lb of steel, 284.86 CY, $230,548.73 sale.
--
-- Source: `06-Walls & Footings` in the LBJ workbook. Every formula below was
-- read from the sheet and reproduced to the digit before any of this was
-- written -- form feet, footing SF, both concrete pours, all four steel terms,
-- sand, excavation and backfill all match exactly.
--
-- ---------------------------------------------------------------------------
-- What one row is
-- ---------------------------------------------------------------------------
--
-- A wall type AND its footing, together. That pairing is the sheet's, and it
-- is right: you do not take off a retaining wall without the footing under it,
-- the two share a length, and the footing's width drives the excavation the
-- wall sits in. Splitting them into two tables would mean keeping two rows in
-- step by hand for no gain.
--
-- It is the third takeoff shape in the system, after the pour (mono_slabs,
-- shared with paving) and the group (pier_groups). Its unit is FORM FEET.
--
-- ---------------------------------------------------------------------------
-- Two mixes on one section -- a first
-- ---------------------------------------------------------------------------
--
-- The wall takes its mix per row (every LBJ row is mix 5, 4000 PSI Ash+Air at
-- $145). The FOOTING takes a single mix for the whole section (the sheet's
-- R8 = 3, 3500 PSI at $140). Cheaper concrete in the ground, better concrete
-- in the wall -- an ordinary decision that no other assembly here has needed.
--
-- So the footing mix lives on the section, exactly where the sheet keeps it.

ALTER TABLE estimate_sections
    ADD COLUMN IF NOT EXISTS footing_mix_design_id integer
        REFERENCES mix_designs(id) ON DELETE SET NULL;

COMMENT ON COLUMN estimate_sections.footing_mix_design_id IS
    'Walls only. The mix every footing in this section is poured from, where '
    'the wall above takes its mix per row. NULL falls back to the row''s wall '
    'mix rather than to nothing -- a footing with no price is a hole.';


CREATE TABLE IF NOT EXISTS wall_runs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections(id) ON DELETE CASCADE,

    label       text,
    description text,

    -- Backfill drives sand, excavation swell and the french drain. The sheet
    -- keeps it as a per-row Y/N, because an interior wall gets none of it.
    backfill    boolean NOT NULL DEFAULT false,

    mix_design_id integer REFERENCES mix_designs(id) ON DELETE SET NULL,

    -- ------------------------------------------------------------ the wall --
    length_ft       numeric(12, 3) NOT NULL DEFAULT 0,
    wall_thick_in   numeric(8, 3)  NOT NULL DEFAULT 0,
    wall_height_in  numeric(8, 3)  NOT NULL DEFAULT 0,

    -- Horizontal steel runs the LENGTH, repeated up the height at this
    -- spacing. Vertical steel runs the HEIGHT, repeated along the length.
    -- "mats" is faces: 2 = both faces of the wall.
    horiz_spacing_in numeric(8, 3),
    horiz_size       integer,
    horiz_mats       integer,
    vert_spacing_in  numeric(8, 3),
    vert_size        integer,
    vert_mats        integer,

    -- --------------------------------------------------------- the footing --
    ftg_width_in    numeric(8, 3) NOT NULL DEFAULT 0,
    ftg_thick_in    numeric(8, 3) NOT NULL DEFAULT 0,
    ftg_spacing_in  numeric(8, 3),
    ftg_size        integer,
    ftg_mats        integer,

    -- -------------------------------------------------------- pilasters -----
    -- UNTESTED. Every LBJ row leaves these empty, so the pilaster terms below
    -- have never run against a real number. Treat the first job with pilasters
    -- as a thing to check rather than a thing to trust -- the same caveat the
    -- pier bell carries.
    pilaster_qty       integer,
    pilaster_length_in numeric(8, 3),
    pilaster_width_in  numeric(8, 3),

    notes      text,
    sort_order integer NOT NULL DEFAULT 0,

    -- --------------------------------------------------------- quantities ---
    calc_form_ff            numeric(14, 4),
    calc_footing_sf         numeric(14, 4),
    calc_wall_concrete_cy   numeric(14, 4),
    calc_footing_concrete_cy numeric(14, 4),
    calc_pilaster_concrete_cy numeric(14, 4),
    calc_concrete_cy        numeric(14, 4),
    calc_horiz_rebar_lb     numeric(14, 3),
    calc_vert_rebar_lb      numeric(14, 3),
    calc_footing_rebar_lb   numeric(14, 3),
    calc_pilaster_rebar_lb  numeric(14, 3),
    calc_total_rebar_lb     numeric(14, 3),
    calc_sand_cy            numeric(14, 3),
    calc_excavate_cy        numeric(14, 3),
    calc_backfill_cy        numeric(14, 3),
    calc_drain_lf           numeric(14, 3),

    -- ------------------------------------------------------------- costs ----
    calc_direct_cost    numeric(14, 2),
    calc_allocated_cost numeric(14, 2),
    calc_equip_fuel     numeric(14, 2),
    calc_tax            numeric(14, 2),
    calc_cost           numeric(14, 2),
    calc_sale           numeric(14, 2),
    calc_cost_per_unit  numeric(12, 4),
    calc_sale_per_unit  numeric(12, 4),

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT wall_runs_length_nonneg CHECK (length_ft >= 0),
    CONSTRAINT wall_runs_wall_nonneg   CHECK (wall_thick_in >= 0 AND wall_height_in >= 0),
    CONSTRAINT wall_runs_ftg_nonneg    CHECK (ftg_width_in >= 0 AND ftg_thick_in >= 0)
);

CREATE INDEX IF NOT EXISTS wall_runs_section_idx ON wall_runs (section_id, sort_order);

COMMENT ON TABLE wall_runs IS
    'One wall type and the footing under it (sql/040). The section is measured '
    'in FORM FEET -- calc_form_ff -- which is contact area on ONE face, not '
    'both: the sheet computes both faces and halves them.';

COMMENT ON COLUMN wall_runs.calc_form_ff IS
    'Contact area / 2. The sheet computes length x height both faces, then '
    'halves it, so "form feet" here is one face of the wall plus the pilaster '
    'returns. That halving is the difference between $5.66/FF and $2.83/FF on '
    'the same job, so do not quietly change the convention.';

COMMENT ON COLUMN wall_runs.calc_footing_rebar_lb IS
    'Both directions. The sheet adds E*(N/P) and (E/P)*N, which look like a '
    'copy-paste duplicate and are not: longitudinal bars are N/P bars each E ft '
    'long, transverse are E*12/P bars each N/12 ft long, and both come to '
    'E*N/P. Verified against the sheet. Do not "fix" it.';


-- ---------------------------------------------------------- assembly rates --
-- Where walls differ from the mono slab. A row here means "this assembly
-- differs"; anything absent falls through to the company setting.

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    -- Labor, all $/FF except the footing (per SF of footing plan area) and
    -- tie steel (per ton).
    ('walls_footings', 'labor_footings_sf',      8.00,  '06 D66 - footing labor per SF of footing'),
    ('walls_footings', 'labor_forming_sf',       3.50,  '06 D67 - per FORM foot'),
    ('walls_footings', 'labor_place_finish_sf',  3.50,  '06 D68'),
    ('walls_footings', 'labor_wreck_sf',         1.00,  '06 D69'),
    ('walls_footings', 'labor_rub_patch_sf',     0.25,  '06 D70 - no equivalent on a slab'),
    ('walls_footings', 'labor_tie_steel_ton',  450.00,  '06 D71'),
    ('walls_footings', 'labor_french_drain_lf', 10.00,  '06 D72'),
    ('walls_footings', 'labor_excavate_cy',     12.00,  '06 D73'),
    ('walls_footings', 'labor_backfill_cy',      8.00,  '06 D74'),

    -- Supervision is TYPED here, as on piers: a wall job''s duration is not a
    -- function of its area. 0 turns the derivation off.
    ('walls_footings', 'labor_super_sf_per_week', 0,    'typed, not derived - see 06 D78'),

    -- Forming lumber is 40% of the form area, against the slab''s 50%.
    ('walls_footings', 'form_percent',           0.40,  '06 S51'),
    ('walls_footings', 'waste_concrete',         0.06,  '06 J51'),
    ('walls_footings', 'waste_rebar',            0.10,  '06 J56 - lap, not waste'),

    -- No vapor barrier, no support steel, no mesh on a wall.
    ('walls_footings', 'support_rebar_lb_per_sf', 0,    'walls carry none'),
    ('walls_footings', 'vapor_barrier_enabled',   0,    'no poly under a wall'),

    ('walls_footings', 'accessories_unit_cost',  0.04,  '06 U85'),
    ('walls_footings', 'sand_unit_cost',        20.00,  '06 F59'),
    ('walls_footings', 'sand_in_under_form',     3.00,  '06 BH - 3" under the form line'),
    ('walls_footings', 'backfill_swell',         1.30,  '06 DF - 30% swell'),

    -- Equipment day rates for this assembly.
    ('walls_footings', 'equip_vault_day_rate',  50.00,  '06 F87'),
    ('walls_footings', 'equip_misc_day_rate',   35.00,  '06 F88'),
    ('walls_footings', 'concrete_pump_cy',      10.00,  '06 F90'),

    -- Lumber divisors that differ from the slab set.
    ('walls_footings', 'lumber_2x4_per_ff',      3.60,  '06 S52 - FF x 3.6 x form%'),
    ('walls_footings', 'lumber_ply_per_ff',      0.0625,'06 S58 - FF x 2/32'),
    ('walls_footings', 'wall_ties_per_ff',       2.25,  '06 S66 - one per 2.25 FF, 50/box'),
    ('walls_footings', 'camlocks_per_ff',        0.55,  '06 S77'),
    ('walls_footings', 'pipe_brace_per_ff',     30.00,  '06 S81 - one per 30 FF'),
    ('walls_footings', 'patch_sf_per_bag',     350.00,  '06 S79'),
    ('walls_footings', 'french_drain_lf_cost',   8.50,  '06 U69 - material, beside the labor line'),
    ('walls_footings', 'water_stop_lf_cost',     1.00,  '06 U67'),
    ('walls_footings', 'chamfer_lf_cost',        0.25,  '06 U65')
ON CONFLICT (kind, key) DO NOTHING;
