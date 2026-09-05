-- 052_cip_deck.sql
--
-- 08-CIP EL. DECK: 32,100 SF of elevated post-tensioned deck on two levels.
-- 1,459.85 CY, 61,715 lb of steel on the sheet, $952,052.02.
--
-- Source: `08-CIP EL. DECK` in the LBJ workbook. Every formula was read and
-- reproduced before any of this was written; the sheet's own nineteen cost
-- columns sum to $952,052.0214 against its stated $952,052.0215, so the model
-- is understood rather than approximated. Full derivation in
-- `docs/specs/cip-deck-spec.md`.
--
-- This is the sixth assembly and the first that HANGS IN THE AIR. The five
-- before it are all ground-bearing, and four things follow from that which
-- nothing else in the app has:
--
--   * shoring and reshoring — the deck has nothing under it
--   * a crane, at $3,200/day and 27 billable days: $136,728, 14% of the
--     section on one line and the largest single equipment figure anywhere
--   * post-tension priced by the square foot, with a supplier quote slot
--     already in the sheet (`N80 = IF(I80=0, SF x 1.45, I80)`) — which is
--     what section_quotes has done since sql/039, so PT becomes a quote kind
--     rather than a column
--   * the labor can be SUBCONTRACTED. On LBJ all ten lines are subbed:
--     $251,654.73, with the own-crew column zero throughout.
--
-- ---------------------------------------------------------------------------
-- What one row is
-- ---------------------------------------------------------------------------
--
-- A LEVEL. The fifth takeoff shape, after the pour, the group, the run and the
-- column type — and the simplest of them: an area, a thickness, two mats of
-- bar, an edge, and up to three grade beams running through it.
--
-- The sheet gives every level TWO rows and sums concrete and steel across the
-- pair (`U10 = (C10*E10/324 + C11*E11/324) * ...`). Row 11 holds only a stray
-- 'l' on LBJ. Asked what the second row was for, Chad: **"dead weight from the
-- source sheet."** So one row per level here, and the pair does not survive.
--
-- ---------------------------------------------------------------------------
-- Supervision is TYPED, and the equipment ladder rides it
-- ---------------------------------------------------------------------------
--
--     mono slab   SF / 16,000 per week x 7 days
--     paving      SF / 25,000 per week x 7 days
--     columns     columns / 20 per week x 5 days
--     piers       typed
--     walls       typed
--     CIP DECK    typed                                <- this
--
-- 60 days on LBJ, which the additive band ladder turns into 90 equipment days
-- and the rental tier into 27 billable units. Both are `equip_days_from_super`
-- and `rental_billable_units` unchanged — the machinery is already here.
--
-- Typed means this assembly inherits the untyped-supervision warning built for
-- audit #5: a deck section with nothing entered has a 0-day rental ladder and
-- every machine reads $0.00 beside a correct rate.
--
-- ---------------------------------------------------------------------------
-- Six things the sheet gets wrong, fixed here
-- ---------------------------------------------------------------------------
--
-- 1. BEAM SLOTS 2 AND 3 CARRY ALMOST NO STEEL. `AL` (slot 1) reads column O,
--    which is lb per LF. `AM` (slot 2) reads column **Q**, which is CY per LF,
--    and `AN` (slot 3) reads column **S**, which is a header cell and empty.
--    So LBJ's level 2 charges **7 lb** for a 45 LF type-2 beam where the
--    honest figure is 2,855.49 — 3,190.88 lb after the beam factor, about
--    $2,244 of steel and $718 of tie-steel labor. Live on this job, and worse
--    on any deck that fills all three slots.
--
-- 2. RESHORING SF IS A HAND-PICKED LIST. `K83 = C10+C12+C14+C16+C22+C24+C28`
--    skips rows 18, 20, 26 and everything past 28. A level entered on one of
--    those rows is reshored for free. LBJ's two levels are on 10 and 12.
--
-- 3. OWN-CREW CABLE PLACEMENT READS AN EMPTY ROW. `K95 = IF(C100="N", D100 x
--    H87, 0)` — row 100 is blank, so the moment you self-perform cable
--    placement the sheet charges $0. That is $23,994.75 on this job.
--
-- 4. BEAM TYPES 4-10 RESOLVE TO DIFFERENT ROWS IN DIFFERENT COLUMNS. Steel
--    maps type 4 to schedule row 56; form feet maps type 4 to row 60. And the
--    7-10 branches are nested INSIDE the =6 branch in every one of them, so a
--    level on beam type 7 gets nothing at all. A beam type here is a foreign
--    key; there is no mapping to get wrong.
--
-- 5. `BD` IS LABELLED TOTAL AND USED AS MIX #10. The mix-CY columns run AT=1
--    to BC=10 by header, but `K73:K77` reads `IF(A=9, BC, IF(A=10, BD))` —
--    off by one — and `BD` is `SUM(AT:AY)`, only mixes 1-6. A job on mix 9 or
--    10 picks up the wrong column and one of them is a partial sum of six
--    others. Same class as the paving `SUM(W10:X41)*3`. LBJ is on mix 8.
--
-- 6. ONE CELL, TWO MEANINGS. `J83` is 1.1, labelled under reshoring and read
--    by BOTH reshoring and form rental shoring. Editing it for one reason
--    moves the other by $4,300. Split into two rules below.
--
-- ---------------------------------------------------------------------------
-- And one thing Chad changed
-- ---------------------------------------------------------------------------
--
-- GRADE BEAM FORM FEET ARE BOTH FACES. The sheet's `U53 = C53/12` is height
-- over twelve — ONE face. Asked whether a deck grade beam is formed on one
-- side only, Chad, 2026-09-04: **"both faces — the sheet is light."** That
-- doubles the section's GB form feet from 240 to 480 and moves LBJ +$2,425.01:
-- $1,440 of GB forming labor, and $985.01 of lumber, because the 2x4, 2x6,
-- 2x10, plywood and stake lines all ride `perm edge LF + GB form FF`.
--
-- The golden fixture therefore lands at $954,477.03 and not the sheet's
-- $952,052.02, deliberately, before the six fixes above are counted.

-- ---------------------------------------------------------------------------
-- The beam schedule reuses estimate_beam_types (sql/025)
-- ---------------------------------------------------------------------------
--
-- Width, height, top / bottom / mid bars, stirrups and L bars are already
-- there and already mean the same things. One field is missing: the deck
-- schedule's L bars are a LENGTH, not a longitudinal count — `(size/16)^2 x
-- const x (12 / spacing) x LENGTH FT` per LF of beam.

ALTER TABLE estimate_beam_types
    ADD COLUMN IF NOT EXISTS l_bars_length_ft numeric(8, 3);

COMMENT ON COLUMN estimate_beam_types.l_bars_length_ft IS
    'CIP deck beam schedule (sql/052): how long each L bar is. The deck sheet '
    'spaces L bars along the beam and gives each one a length, where a mono '
    'slab beam counts them longitudinally. NULL keeps the mono-slab reading.';


-- ---------------------------------------------------------------------------
-- Deck levels
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS deck_levels (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections(id) ON DELETE CASCADE,

    label       text,
    description text,

    -- The section's unit is SF and this is what it counts. It is also the
    -- allocation basis: every shared cost on this assembly spreads by area
    -- (the sheet's BU:BY all divide by C50), same as the mono slab and unlike
    -- columns (form SF) or walls (form feet).
    area_sf       numeric(14, 3) NOT NULL DEFAULT 0 CHECK (area_sf >= 0),
    thickness_in  numeric(8, 3)  NOT NULL DEFAULT 0 CHECK (thickness_in >= 0),

    -- Post-tensioned? The sheet's `BE10 = IF(F10="N", 0, C10)` — PT SF is the
    -- area of the levels that carry cable, not the whole deck.
    has_cable   boolean NOT NULL DEFAULT false,

    mix_design_id integer REFERENCES mix_designs(id) ON DELETE SET NULL,

    -- Permanent edge. Drives the edge / safety rail labor line and, with the
    -- grade beam form feet, every lumber line on the section.
    perm_edge_lf  numeric(14, 3) NOT NULL DEFAULT 0 CHECK (perm_edge_lf >= 0),

    -- ------------------------------------------------------------- the mats --
    -- Two-way mats, top and bottom. A mat with no size or no spacing
    -- contributes nothing rather than contributing a zero-weight bar.
    --     LF of bar = 2 / (spacing_in / 12) x area
    top_bar_size        smallint CHECK (top_bar_size IS NULL OR top_bar_size > 0),
    top_bar_spacing_in  numeric(8, 3) CHECK (top_bar_spacing_in IS NULL OR top_bar_spacing_in > 0),
    bot_bar_size        smallint CHECK (bot_bar_size IS NULL OR bot_bar_size > 0),
    bot_bar_spacing_in  numeric(8, 3) CHECK (bot_bar_spacing_in IS NULL OR bot_bar_spacing_in > 0),

    mesh_sf     numeric(14, 3) NOT NULL DEFAULT 0 CHECK (mesh_sf >= 0),

    -- Two takeoff quantities the sheet reaches for across tabs rather than
    -- entering (`H79 = BQ68` points at the Skyline block). They are per-level
    -- facts, so they are entered per level: stud rails carry both a material
    -- line at $1.65/lb and a labor line at $500/ton, and carton forms a
    -- material line at $0.85/SF. Both are zero on LBJ. Asked whether stud
    -- rails were a real line or furniture like the columns cure and saw
    -- cutting, Chad, 2026-09-04: **"real - keep it."**
    stud_rail_lb    numeric(14, 3) NOT NULL DEFAULT 0 CHECK (stud_rail_lb >= 0),
    carton_form_sf  numeric(14, 3) NOT NULL DEFAULT 0 CHECK (carton_form_sf >= 0),

    notes       text,
    sort_order  integer NOT NULL DEFAULT 0,

    -- ------------------------------------------------------------- derived --
    calc_slab_cy        numeric(14, 4),
    calc_beam_cy        numeric(14, 4),
    calc_concrete_cy    numeric(14, 4),
    calc_slab_rebar_lb  numeric(14, 3),
    calc_beam_rebar_lb  numeric(14, 3),
    calc_total_rebar_lb numeric(14, 3),
    calc_pt_sf          numeric(14, 3),
    calc_pt_lb          numeric(14, 3),
    calc_gb_form_ff     numeric(14, 3),
    calc_beam_lf        numeric(14, 3),

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

CREATE INDEX IF NOT EXISTS deck_levels_section_idx
    ON deck_levels (section_id, sort_order);

COMMENT ON TABLE deck_levels IS
    'One level of a cast-in-place elevated deck (sql/052). The fifth takeoff '
    'shape. The workbook gives each level two rows and sums across the pair; '
    'Chad, 2026-09-04, on what the second row is for: "dead weight from the '
    'source sheet." One row per level here.';

COMMENT ON COLUMN deck_levels.calc_gb_form_ff IS
    'Grade beam contact area: sum over the level''s beams of LN FT x height/12 '
    'x 2 -- BOTH faces. The sheet''s U53 is height/12, one face. Chad, '
    '2026-09-04: "both faces - the sheet is light." Worth +$2,425.01 on LBJ, '
    'because this figure also drives every lumber line on the section.';

COMMENT ON COLUMN deck_levels.calc_beam_rebar_lb IS
    'Every beam on the level, all three slots. The sheet reads lb/LF for slot '
    '1, CY/LF for slot 2 and an empty header cell for slot 3, so LBJ charges '
    '7 lb for a 45 LF beam that weighs 2,855.49.';


-- ---------------------------------------------------------------------------
-- Which beams run through which level
-- ---------------------------------------------------------------------------
--
-- Same shape as grade_beams (sql/025): the schedule lives once on
-- estimate_beam_types and this is the join plus a length. The sheet has three
-- fixed slots per level; there is no reason for a limit here, and three fixed
-- slots is exactly how it ended up reading the wrong column for two of them.

CREATE TABLE IF NOT EXISTS deck_level_beams (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_level_id uuid NOT NULL REFERENCES deck_levels(id) ON DELETE CASCADE,
    beam_type_id  uuid NOT NULL REFERENCES estimate_beam_types(id) ON DELETE CASCADE,
    length_lf     numeric(14, 3) NOT NULL DEFAULT 0 CHECK (length_lf >= 0),
    notes         text,
    sort_order    integer NOT NULL DEFAULT 0,

    calc_rebar_lb   numeric(14, 3),
    calc_concrete_cy numeric(14, 4),
    calc_form_ff    numeric(14, 3),

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS deck_level_beams_level_idx
    ON deck_level_beams (deck_level_id, sort_order);


-- ---------------------------------------------------------------------------
-- Subcontracted labor
-- ---------------------------------------------------------------------------
--
-- The sheet decides this per LINE — column C is Y/N on each of the ten labor
-- rows and routes that row's money to one of two buckets. Asked whether he
-- would ever sub the forming and self-perform the tie steel, Chad, 2026-09-04:
-- **one switch per section**.
--
-- So the switch lives here and the flag lives on the line, set from it at
-- refresh. Per-line is then a UI change and a default, not a migration — and
-- the LBJ case (all ten subbed) is exactly one checkbox.
--
-- Costing does not care: subbed labor is still labor, untaxed and carrying no
-- fuel. What it buys is the ability to say what the sub is being asked to
-- price, which is what the workbook's SUB LABOR SHEET tab is for.

ALTER TABLE estimate_sections
    ADD COLUMN IF NOT EXISTS labor_subcontracted boolean NOT NULL DEFAULT false;

ALTER TABLE estimate_labor_lines
    ADD COLUMN IF NOT EXISTS subcontracted boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN estimate_sections.labor_subcontracted IS
    'Is this section''s field labor subcontracted? (sql/052) The CIP deck '
    'sheet decides it per line; Chad, 2026-09-04, asked whether that is real: '
    'one switch per section. Supervision is never subbed - the sheet has no '
    'Y/N on the supervision block either.';


-- ---------------------------------------------------------------------------
-- One catalog item this assembly needs and the catalog does not have
-- ---------------------------------------------------------------------------
--
-- PAVECRETE is a bagged patch mix, one bag per 1,200 SF of deck (08 S104), at
-- $15 (08 U104). It is not PATCH MATERIAL, which the catalog already carries
-- at $45 -- and reaching for that one by name is exactly how the columns
-- CHAIRS line ended up buying METAL CHAIRS at $45 instead of SLAB CHAIRS at
-- $27 (audit #7). So it is its own row, the way sql/044 added FRENCH DRAIN and
-- WATER STOP.

INSERT INTO materials (name, category, unit, unit_cost, unit_note, price_as_of, sort_order)
VALUES
    ('PAVECRETE', 'chemical', 'BAG', 15.0000,
     'Bagged patch mix, one bag per 1,200 SF of deck -- 08-CIP EL. DECK U104',
     '2026-09-04', 702)
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------------
-- Rates. NO PRICES -- see sql/044 and docs/specs/design-decisions.md.
-- Concrete, steel, PT, lumber and accessories all resolve through the catalog.
--
-- Everything here is read off the sheet's own cells, cited. Keys that already
-- exist company-wide (labor_forming_sf, saw_cutting_lf, concrete_pump_cy,
-- out_of_town_day_rate, waterproofing_sf) are repeated ONLY where this
-- assembly's number differs from the company's.
-- ---------------------------------------------------------------------------

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    -- Labor. Four run off deck area, the rest off their own driver.
    ('cip_deck', 'labor_forming_sf',           4.75,  '08 D87'),
    ('cip_deck', 'labor_place_finish_sf',      0.50,  '08 D88'),
    ('cip_deck', 'labor_wreck_sf',             0.45,  '08 D89'),
    ('cip_deck', 'labor_reshoring_sf',         0.35,  '08 D90'),
    ('cip_deck', 'labor_edge_rails_lf',        6.00,  '08 D91 - perm edge LF'),
    ('cip_deck', 'labor_gb_forming_ff',        6.00,  '08 D92'),
    ('cip_deck', 'labor_rub_patch_sf',         0.25,  '08 D93'),
    ('cip_deck', 'labor_stud_rails_ton',     500.00,  '08 D94'),
    ('cip_deck', 'labor_cable_placement_lb',   0.65,  '08 D95 - SF x 1.15 lb'),
    ('cip_deck', 'labor_tie_steel_ton',      450.00,  '08 D96 - every pound'),

    -- Supervision is TYPED, like piers and walls. 60 days on LBJ.
    ('cip_deck', 'labor_super_sf_per_week',    0,     'typed - no area derivation'),
    ('cip_deck', 'labor_super_days_per_week',  7.00,  'seven-day week when derived'),

    -- Materials priced per unit of DECK, not per catalog row.
    ('cip_deck', 'pt_cable_sf',                1.45,  '08 F80 - or a PT quote'),
    ('cip_deck', 'stud_rails_lb',              1.65,  '08 F79'),
    ('cip_deck', 'carton_forms_sf',            0.85,  '08 F81'),
    ('cip_deck', 'plywood_forming_sf',         1.50,  '08 J82 - $/SF of coverage'),
    ('cip_deck', 'form_rental_shoring_sf',     1.25,  '08 F84'),
    -- reshoring_material_sf is DELIBERATELY ABSENT. The sheet's F83 is blank,
    -- so that line prices at $0 while its labor prices at $11,235. A blank is
    -- not a price of zero (design decision 5): the section reports it as
    -- unpriced until somebody types a number.

    -- Contract services. Only pumping has a quantity on LBJ.
    ('cip_deck', 'engineering_sf',             1.05,  '08 F112'),
    ('cip_deck', 'saw_cutting_lf',             2.50,  '08 F113'),
    ('cip_deck', 'concrete_pump_cy',          10.00,  '08 F114 - half the columns rate'),
    ('cip_deck', 'freight_load',            1100.00,  '08 F115'),
    ('cip_deck', 'waterproofing_sf',           2.25,  '08 F116'),
    ('cip_deck', 'out_of_town_day_rate',     225.00,  '08 F117'),
    ('cip_deck', 'barricades_lf',              1.45,  '08 F118'),

    -- Equipment day rates with no catalog item to carry them. The crane is
    -- the largest single equipment figure in the app.
    ('cip_deck', 'equip_crane_day_rate',    3200.00,  '08 F106'),
    ('cip_deck', 'equip_20_ton_lift_day_rate', 850.00,'08 F105 - 0 days on LBJ'),
    ('cip_deck', 'equip_misc_day_rate',       35.00,  '08 F110'),

    -- ------------------------------------------------------------- rules --
    ('cip_deck', 'waste_concrete',             0.04,  '08 J73'),
    ('cip_deck', 'waste_rebar',                0.10,  '08 J78'),
    -- Applied to beam steel ON TOP of waste_rebar, which the schedule row has
    -- already carried. 1.10 x 1.12 = 1.232 on a grade beam bar.
    ('cip_deck', 'waste_rebar_beams',          0.12,  '08 AO = SUM(...) x 1.12'),
    ('cip_deck', 'pt_lb_per_sf',               1.15,  '08 H95'),
    ('cip_deck', 'form_percent',               0.50,  '08 F82 - "OF COVERAGE"'),

    -- The two halves of J83, which is one cell doing two jobs.
    ('cip_deck', 'reshoring_multiplier',       1.10,  '08 J83, as labelled'),
    ('cip_deck', 'form_rental_shoring_multiplier', 1.10, '08 J83, silently reused'),

    -- Lumber and consumable divisors, off the sheet's own formulas. Every one
    -- of these rides `perm edge LF + GB form FF`, not deck area.
    ('cip_deck', 'lumber_2x4_per_lf',          1.00,  '08 S73 = edge + GB ff'),
    ('cip_deck', 'lumber_2x6_per_lf',          1.00,  '08 S74 = S73'),
    ('cip_deck', 'lumber_2x10_per_lf',         0.20,  '08 S78'),
    ('cip_deck', 'lumber_ply_per_lf',          0.015625, '08 S80 = edge+ff / 64'),
    ('cip_deck', 'stakes_2x10_lf_per_stake',  25.00,  '08 S81 = ROUND(S78/25)'),
    ('cip_deck', 'stakes_per_bundle',          2.00,  '08 S81 x 0.5'),
    ('cip_deck', 'nails_edge_factor',          1.25,  '08 S82/S83'),
    ('cip_deck', 'nails_16p_per_sf',        1500.00,  '08 S82 - per EDGE LF here'),
    ('cip_deck', 'nails_8p_per_sf',         3000.00,  '08 S83 - 6p matches 8p'),
    ('cip_deck', 'pavecrete_sf_per_bag',    1200.00,  '08 S104'),
    ('cip_deck', 'chairs_sf_per_bag',      15000.00,  '08 S107'),
    ('cip_deck', 'cure_sf_per_gal',          300.00,  '08 S114 = SF/300/55'),
    ('cip_deck', 'accessories_stud_rail_factor', 0.75,'08 S109 = steel + rails x .75'),

    -- Nothing a deck has.
    ('cip_deck', 'support_rebar_lb_per_sf',    0,     'the mats are the steel'),
    ('cip_deck', 'vapor_barrier_enabled',      0,     'nothing goes under a deck'),
    ('cip_deck', 'haul_off_cy',                0,     'nothing is excavated')
ON CONFLICT (kind, key) DO NOTHING;
