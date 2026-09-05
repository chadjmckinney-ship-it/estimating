-- 037: piers
--
-- Phase 3b. Read off 01-Piers in the LBJ workbook; the full derivation is in
-- docs/specs/piers-spec.md. Acceptance is 106 piers / 2,348 LF / 632.6993 CY
-- against $295,601.21, taxable at 8.25%, 18% markup.
--
-- Piers is the first assembly that is NOT a pour. Paving fitted into
-- mono_slabs because a paving area has SF, a thickness, sand, a mix and a bar
-- mat — it IS a pour. A pier has none of those. Its unit is EA and its
-- quantity is a count.
--
-- That matters more than the table does, because costing spreads a section's
-- shared cost across its pours WEIGHTED BY SF. With every weight at zero,
-- allocate_amount puts the whole lot on whichever row sorts last and reports a
-- per-unit cost that is nonsense for every other row — no error, nothing wrong
-- on screen. So this migration comes with a change to costing: an allocation
-- basis per assembly, SF for slabs and paving, EA for piers.

BEGIN;

-- ------------------------------------------------------- pier groups -------
--
-- One row is a GROUP of identical piers, not one pier — the same shape as
-- estimate_beam_types. Six groups make LBJ's 106.

CREATE TABLE pier_groups (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections (id) ON DELETE CASCADE,
    label       text,
    description text,

    qty                 integer NOT NULL CHECK (qty >= 0),
    diameter_in         numeric(8, 2) NOT NULL CHECK (diameter_in > 0),
    base_depth_ft       numeric(10, 3) NOT NULL DEFAULT 0 CHECK (base_depth_ft >= 0),
    rock_penetration_ft numeric(10, 3) NOT NULL DEFAULT 0 CHECK (rock_penetration_ft >= 0),
    bell_size_in        numeric(8, 2) CHECK (bell_size_in IS NULL OR bell_size_in >= 0),
    mix_design_id       integer REFERENCES mix_designs (id) ON DELETE SET NULL,

    -- The cage. Vertical bars run the hole; ties hoop them; dowels are the
    -- connection up into whatever lands on the pier.
    vert_bars_count     smallint CHECK (vert_bars_count IS NULL OR vert_bars_count >= 0),
    vert_bars_size      smallint REFERENCES bar_weights (bar_size),
    tie_size            smallint REFERENCES bar_weights (bar_size),
    tie_spacing_in      numeric(8, 3) CHECK (tie_spacing_in IS NULL OR tie_spacing_in > 0),
    -- Confinement at the top, called out on the drawing as a COUNT at a
    -- spacing — "3 #3 stirrups at 3 inches top" — not as a band length.
    band_tie_count      smallint CHECK (band_tie_count IS NULL OR band_tie_count >= 0),
    band_spacing_in     numeric(8, 3) CHECK (band_spacing_in IS NULL OR band_spacing_in > 0),
    dowels_count        smallint CHECK (dowels_count IS NULL OR dowels_count >= 0),
    dowels_size         smallint REFERENCES bar_weights (bar_size),
    dowels_length_ft    numeric(10, 3) CHECK (dowels_length_ft IS NULL OR dowels_length_ft >= 0),

    notes       text,
    sort_order  integer NOT NULL DEFAULT 0,

    -- ------------------------------------------------------- quantities ----
    calc_total_depth_ft     numeric(14, 3),
    calc_total_lf           numeric(14, 3),
    calc_shaft_concrete_cy  numeric(14, 4),
    calc_bell_concrete_cy   numeric(14, 4),
    calc_concrete_cy        numeric(14, 4),
    calc_tie_count          numeric(14, 3),
    calc_vert_rebar_lb      numeric(14, 3),
    calc_tie_rebar_lb       numeric(14, 3),
    calc_dowel_rebar_lb     numeric(14, 3),
    calc_total_rebar_lb     numeric(14, 3),
    calc_drill_lf_rate      numeric(12, 4),
    calc_drill_cost         numeric(14, 2),

    -- ------------------------------------------------------------ cost -----
    calc_direct_cost    numeric(14, 2),
    calc_allocated_cost numeric(14, 2),
    calc_equip_fuel     numeric(14, 2),
    calc_tax            numeric(14, 2),
    calc_cost           numeric(14, 2),
    calc_sale           numeric(14, 2),
    calc_cost_per_unit  numeric(12, 4),
    calc_sale_per_unit  numeric(12, 4),

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pier_groups_section_idx ON pier_groups (section_id, sort_order);

COMMENT ON TABLE pier_groups IS
    'One row = a group of identical drilled piers on a piers section (sql/037). '
    'Quantities are stored, not derived on read, like every other calc_ column '
    'in this system.';
COMMENT ON COLUMN pier_groups.qty IS 'Piers in this group. The section is measured in EA.';
COMMENT ON COLUMN pier_groups.band_tie_count IS
    'Confinement ties at the top, as the drawing calls them out: a COUNT at '
    'band_spacing_in, e.g. 3 #3 at 3" o.c. NULL = no band.';
COMMENT ON COLUMN pier_groups.calc_drill_cost IS
    'Drilling, from pier_drill_rates by diameter x LF. The workbook computes '
    'the same figure in a hidden block and lets a real quote override it.';

-- ------------------------------------------------- drilling rate table -----
--
-- The workbook's $58,032 "PIER QUOTE" is not a quote — it is this table,
-- summed. 564 LF of 24" at $8 + 1,104 LF of 36" at $30 + 680 LF of 42" at $30.
-- A typed quote overrides it (estimate_sections.pier_drill_quote below), which
-- is what the sheet's IF(J54="", computed, J54) does.
--
-- Casing and deduct are carried because the sheet carries them, but only
-- drilling reaches the section cost: casing is a unit rate for the bid form,
-- priced only when a job actually needs it.

CREATE TABLE pier_drill_rates (
    diameter_in     numeric(8, 2) PRIMARY KEY,
    drill_per_lf    numeric(12, 4) NOT NULL,
    casing_per_lf   numeric(12, 4) NOT NULL DEFAULT 0,
    deduct_per_lf   numeric(12, 4) NOT NULL DEFAULT 0,
    note            text,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

INSERT INTO pier_drill_rates (diameter_in, drill_per_lf, casing_per_lf, deduct_per_lf, note) VALUES
    (16, 10, 6,   0, '01-Piers hidden rate table, row 52/54'),
    (18,  8, 24,  0, '01-Piers hidden rate table, row 52/54'),
    (24,  8, 30,  0, '01-Piers hidden rate table, row 52/54'),
    (30, 24, 35,  0, '01-Piers hidden rate table, row 52/54'),
    (36, 30, 45,  0, '01-Piers hidden rate table, row 52/54'),
    (42, 30, 60,  0, '01-Piers hidden rate table, row 52/54'),
    (48, 35, 80,  0, '01-Piers hidden rate table, row 52/54'),
    (54, 36, 100, 0, '01-Piers hidden rate table, row 52/54');

COMMENT ON TABLE pier_drill_rates IS
    'Drilling / casing $ per linear foot by shaft diameter. A diameter with no '
    'row here prices at 0 and the line says so — it does not silently '
    'interpolate, because a made-up drilling rate on a 106-pier job is a '
    'five-figure error nobody would see.';

-- ------------------------------------------- a drilling quote, if you get one

ALTER TABLE estimate_sections
    ADD COLUMN IF NOT EXISTS pier_drill_quote numeric(14, 2);

COMMENT ON COLUMN estimate_sections.pier_drill_quote IS
    'A real drilling quote for this section. When set it REPLACES the figure '
    'computed from pier_drill_rates, exactly as the sheet''s J54 does.';

-- ------------------------------------------------- piers assembly rates ----
--
-- A row here means "this assembly DIFFERS" (sql/035). Piers differs a lot.

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('piers', 'waste_concrete',          0.06, 'Sheet 01-Piers K49'),
    ('piers', 'waste_rebar',             0.10, 'Sheet 01-Piers K53'),

    -- Cut to length and field tied, so waste_rebar is genuinely waste here —
    -- drops and mis-cuts. On a slab mat the same column carries the LAP. Same
    -- field, two meanings, decided by the assembly. Do not unify them.
    ('piers', 'rebar_cost_per_lb',       0.75, 'Sheet 01-Piers G53 (paving 0.55, slab 0.60)'),

    -- The cage geometry. These do not vary row to row, so they are rates
    -- rather than columns on the grid.
    ('piers', 'pier_cover_in',            1.5, 'Cover to the tie, each side'),
    ('piers', 'pier_tie_hook_in',        12.0, 'Lap / hook on each tie hoop. The sheet has none; '
                                               'sql/023 already allows for this on grade beam stirrups'),
    ('piers', 'pier_bottom_cover_in',       0, 'Bar runs the full hole depth, as the sheet has it. '
                                               'Set it if the cage is held up off the bottom'),
    ('piers', 'pier_band_tie_count',        3, 'Default confinement ties at the top'),
    ('piers', 'pier_band_spacing_in',       3, 'Default confinement spacing'),
    ('piers', 'pier_bell_cost_per_in',    4.5, 'Sheet 01-Piers AR45'),

    -- Labor is per EACH on this sheet, not per SF.
    ('piers', 'labor_layout_ea',           50, 'Sheet 01-Piers E57'),
    ('piers', 'labor_place_finish_ea',     50, 'Sheet 01-Piers E58'),
    ('piers', 'labor_cleanup_ea',          50, 'Sheet 01-Piers E59'),
    ('piers', 'labor_excavation_cy',        0, 'Sheet 01-Piers E60 — blank on this job'),
    ('piers', 'labor_tie_steel_ton',      450, 'Sheet 01-Piers E61'),
    ('piers', 'labor_pier_cap_ea',         60, 'Sheet 01-Piers E62'),
    -- Piers has no support-steel allowance, so tie steel bills every pound.
    ('piers', 'support_rebar_lb_per_sf',    0, 'No support steel on a pier cage'),
    ('piers', 'labor_tie_steel_free_lb_per_sf', 0, 'Every pound is tied'),
    ('piers', 'vapor_barrier_enabled',      0, 'No poly on 01-Piers'),

    -- Supervision days are TYPED on this sheet — there is no SF to divide, so
    -- no duration can be derived. 0 means "nobody has said yet", and the
    -- equipment ladder rides whatever is entered.
    ('piers', 'labor_super_sf_per_week',    0, 'Days are entered, not derived'),

    -- Equipment. Vault is $50/day here against the company $25, and both vault
    -- and miscellaneous carry no fuel or tax on this sheet.
    ('piers', 'equip_vault_day_rate',      50, 'Sheet 01-Piers G75'),
    ('piers', 'equip_misc_day_rate',       35, 'Sheet 01-Piers G76'),

    -- Contract services.
    ('piers', 'surveying_ea',              25, 'Sheet 01-Piers E78'),
    ('piers', 'concrete_pump_cy',          20, 'Sheet 01-Piers E80'),
    ('piers', 'haul_off_cy',                4, 'Sheet 01-Piers E81'),
    ('piers', 'haul_off_swell',           1.3, 'Sheet 01-Piers G81 — spoil swells 30%'),
    ('piers', 'out_of_town_day_rate',     250, 'Sheet 01-Piers G82'),
    ('piers', 'demo_lf',                    0, 'Sheet 01-Piers — blank on this job'),

    -- Accessories are $0.04/lb here, as on the slab sheet; paving buys at 0.02.
    ('piers', 'accessories_unit_cost',   0.04, 'Sheet 01-Piers U75')
ON CONFLICT (kind, key) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- What this build does that the sheet does not, and why
--
--   + 12" hook or lap on every tie hoop        +1,165 lb   +$1,259
--   + 3 #3 confinement ties at 3" at the top     +763 lb     +$824
--                                             ----------  ---------
--                                              +2,020 lb   +$2,182   (+2.8%)
--
-- Both were asked for. The sheet ties one spacing top to bottom on all 106
-- piers and treats each hoop as a bare circle.
--
-- Two things deliberately NOT changed: the vertical bars still run the full
-- hole depth (cut to length, no lap, no bottom cover), and the projection up
-- into the cap is still the DOWELS column, which is what it always was.
--
-- Verify:
--   SELECT kind, key, value, note FROM assembly_rates WHERE kind = 'piers'
--   ORDER BY key;
--   SELECT * FROM pier_drill_rates ORDER BY diameter_in;
