-- 077_panels.sql
--
-- 12-PANELS: tilt-wall panels as a takeoff shape of their own — a panel TYPE
-- and how many of it, the seventh shape. Source: the LBJ workbook's 12-PANELS
-- tab, seeded by Chad on 2026-09-08 ("lets do panels, I can seed a couple of
-- panels real quick.. ok, its in the LBJ workbook"): twelve types, three of
-- each, all 7.25" on mix 5 — 36 panels, 30,024 SF, 673.57 CY, 124,024 lb,
-- $411,101.45 cost and $485,099.71 sale at 18%. Only the twelve rows, the mix
-- slot and the forty superintendent days are typed on that tab; every rate is
-- the template's, and this file seeds them. docs/specs/panels-spec.md.
--
-- The row (the tab's row 10): mix, length, thickness, top and bottom
-- elevation, an opening as L x W, horizontal and vertical mats as a spacing,
-- a size and a count of mats, edge bars and corner bars as a count and a size.
-- FOUR opening slots here where the tab has one. Chad, 2026-09-08: "add more
-- opening fields.. right now we have to figure total opening size if more
-- than 1 opening so it is actually short on rebar and lumber for the
-- openings.. 4 openings total per panel type". Each opening deducts its area
-- from the concrete, adds one more set of the panel's edge bars (the tab's
-- IF(I10>0) term, once per opening rather than once per panel, with its
-- dropped bracket closed), and adds its perimeter to the formed perimeter
-- the lumber and the chamfer run off — the tab has no opening lumber at all.
--
-- Measured and sold in SF, GROSS — the tab's W column; openings come off the
-- concrete, not off the area the labor is priced on — and shared cost
-- allocates by that SF. Supervision is TYPED (D88), a foreman for every
-- superintendent day (D89 = D88), expense the same, no PM. The equipment
-- ladder rides those days: sky track, mini excavator, skid steer, compactor
-- and miscellaneous, the trencher parked.

CREATE TABLE IF NOT EXISTS panel_types (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections (id) ON DELETE CASCADE,

    label       text,
    description text,

    -- How many of this panel. The section's SF is SF each x this, the
    -- lifting and bracing inserts count it, and the engineering counts the
    -- types that have any.
    qty         integer NOT NULL DEFAULT 0 CHECK (qty >= 0),

    mix_design_id integer REFERENCES mix_designs (id) ON DELETE SET NULL,

    -- ------------------------------------------------------------ geometry --
    -- The tab's D, E, F and G. Height is top less bottom; a bottom elevation
    -- below grade is negative, as the tab types it (-4).
    length_ft     numeric(12, 3) NOT NULL DEFAULT 0,
    thickness_in  numeric(8, 3)  NOT NULL DEFAULT 0,
    top_el_ft     numeric(12, 3) NOT NULL DEFAULT 0,
    bot_el_ft     numeric(12, 3) NOT NULL DEFAULT 0,

    -- ------------------------------------------------------------ openings --
    -- Up to four per panel, each L x W in feet. A slot with no length or no
    -- width is no opening.
    open1_len_ft  numeric(8, 3),
    open1_wide_ft numeric(8, 3),
    open2_len_ft  numeric(8, 3),
    open2_wide_ft numeric(8, 3),
    open3_len_ft  numeric(8, 3),
    open3_wide_ft numeric(8, 3),
    open4_len_ft  numeric(8, 3),
    open4_wide_ft numeric(8, 3),

    -- --------------------------------------------------------------- steel --
    -- The tab's K..T: two mats at a spacing, edge bars, corner bars.
    horiz_spacing_in numeric(8, 3),
    horiz_size       smallint REFERENCES bar_weights (bar_size),
    horiz_mats       integer,
    vert_spacing_in  numeric(8, 3),
    vert_size        smallint REFERENCES bar_weights (bar_size),
    vert_mats        integer,
    edge_bar_count   integer,
    edge_bar_size    smallint REFERENCES bar_weights (bar_size),
    corner_bar_count integer,
    corner_bar_size  smallint REFERENCES bar_weights (bar_size),

    notes       text,
    sort_order  integer NOT NULL DEFAULT 0,

    -- ----------------------------------------------------------- quantities --
    -- Stored, not derived on read — one writer (refresh_panel_type_calcs).
    calc_height_ft      numeric(12, 3),   -- top - bottom
    calc_sf_each        numeric(14, 3),   -- L x H, gross (the tab's W)
    calc_sf             numeric(14, 3),   -- x qty (AR)
    calc_opening_sf     numeric(14, 3),   -- sum of the openings' areas x qty
    calc_opening_lf     numeric(14, 3),   -- sum of the openings' perimeters x qty
    calc_perimeter_lf   numeric(14, 3),   -- (2L + 2H) x qty (AT)
    calc_bottom_lf      numeric(14, 3),   -- L x qty (AU) — carton forms, durrock, backfill
    calc_concrete_cy    numeric(14, 4),   -- (L x H - openings) x thk / 324 x qty, with waste
    calc_steel_each_lb  numeric(14, 3),   -- one panel, with waste (U)
    calc_total_rebar_lb numeric(14, 3),   -- x qty (AQ)

    -- ----------------------------------------------------------------- cost --
    calc_direct_cost    numeric(14, 2),
    calc_allocated_cost numeric(14, 2),
    calc_equip_fuel     numeric(14, 2),
    calc_tax            numeric(14, 2),
    calc_cost           numeric(14, 2),
    calc_sale           numeric(14, 2),
    calc_cost_per_unit  numeric(14, 4),   -- per SF
    calc_sale_per_unit  numeric(14, 4),

    updated_by  uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS panel_types_section_idx       ON panel_types (section_id);
-- Every FK that can be deleted through carries an index (sql/067); the
-- bar-size columns are the one exception, as on beam_runs.
CREATE INDEX IF NOT EXISTS panel_types_mix_design_id_idx ON panel_types (mix_design_id);
CREATE INDEX IF NOT EXISTS panel_types_updated_by_idx    ON panel_types (updated_by);

COMMENT ON TABLE panel_types IS
    'One tilt-wall panel type and its quantity (sql/077). Measured in SF, gross of '
    'openings; shared cost allocates by that SF. Four opening slots per type.';
COMMENT ON COLUMN panel_types.calc_sf_each IS
    'L x H, GROSS — the tab''s W column. Openings come off the concrete (calc_concrete_cy), '
    'not off the area the $/SF labor is priced on or the section allocates by.';
COMMENT ON COLUMN panel_types.calc_steel_each_lb IS
    'The tab''s U: both mats, the edge bars, one more set of edge bars PER OPENING (the '
    'tab''s IF(I10>0) term with its dropped bracket closed), the corner bars, with waste. '
    'Catalog bar weights, not (size/16)^2 x 10.7028.';
COMMENT ON COLUMN panel_types.calc_opening_lf IS
    'The openings'' perimeters x qty. Joins the formed perimeter the lumber and the '
    'chamfer run off — the tab carries no opening lumber (Chad, 2026-09-08).';


-- ---------------------------------------------------------------------------
-- Rates: the tab's, which are the template's. Section-level keys only — the
-- equipment day rates, the supervision day rates and the out-of-town per diem
-- are the job's (price_book.ESTIMATE_LEVEL_KEYS) and are not seeded per kind.
-- ---------------------------------------------------------------------------

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    -- Labor, per SF of gross panel area (12 D80-D83), the steel per ton, the
    -- backfill per CY of the trench along the panel line (H85), the ledge typed.
    ('panels', 'labor_brick_ledge_lf',        1.50,  '12 D79 — LF typed'),
    ('panels', 'labor_forming_sf',            0.35,  '12 D80'),
    ('panels', 'labor_place_finish_sf',       0.65,  '12 D81'),
    ('panels', 'labor_wreck_sf',              0.25,  '12 D82'),
    ('panels', 'labor_rub_patch_sf',          0.85,  '12 D83'),
    ('panels', 'labor_tie_steel_ton',       450.00,  '12 D84 — every pound'),
    ('panels', 'labor_backfill_cy',           8.00,  '12 D85'),
    ('panels', 'backfill_width_ft',           6.50,  '12 H85: bottom LF x 6.5 x depth / 27'),
    ('panels', 'backfill_depth_ft',           2.00,  '12 G85'),

    -- Supervision is typed (D88); the foreman and the expense ride it.
    ('panels', 'labor_super_sf_per_week',     0,     'panels type their days (12 D88)'),
    ('panels', 'labor_super_days_per_week',   7,     'seven-day weeks on the ladder'),

    -- Waste and forming.
    ('panels', 'waste_concrete',              0.04,  '12 J66'),
    ('panels', 'waste_rebar',                 0.05,  '12 J69'),
    ('panels', 'carton_forms_waste',          0.10,  '12 J75 — carton forms and the retainer'),
    ('panels', 'form_percent',                0.40,  '12 S66 — % OF FORMING on the perimeter lumber'),
    ('panels', 'form_rental_percent',         0,     '12 J77 — blank'),
    ('panels', 'corner_bar_ft',               4.00,  '12 U: corner bars x 4 ft x lb/ft'),
    ('panels', 'panel_2x8_thick_in',          6.00,  '12 AV/AW: 2x6 under 6", 2x8 from 6"'),

    -- Lumber and consumable divisors off the tab''s own formulas.
    ('panels', 'lumber_2x10_per_lf',          1.00,  '12 S70 — per bottom LF; the tab sums the type lengths and forgets the count'),
    ('panels', 'stakes_lf_per_bundle',      100.00,  '12 S72 = 2x8 LF / 100 x form%'),
    ('panels', 'nails_16p_per_sf',         1800.00,  '12 S73 = ROUNDUP((2x8 + 2x6) / form% / 1800)'),
    ('panels', 'nails_8p_factor',             0.60,  '12 S74 = 16p x 0.6; 6p = 8p'),
    ('panels', 'patch_sf_per_bag',          250.00,  '12 S89 — Pave Crete, SF / 250'),
    ('panels', 'chairs_sf_per_bag',        6000.00,  '12 S92 — panel chairs, ROUNDUP(SF / 6000)'),
    ('panels', 'lift_inserts_per_panel',      8.00,  '12 S95'),
    ('panels', 'brace_inserts_per_panel',     3.00,  '12 S96'),
    ('panels', 'cure_sf_per_gal',           300.00,  '12 S100 — ROUNDUP(SF / 300 / 55)'),
    ('panels', 'bond_breaker_sf_per_gal',   200.00,  '12 S101 — SF / 200 / 55, not rounded'),

    -- Along the bottom of every panel (12 F75, F76), the rental blank (F77).
    ('panels', 'carton_forms_lf',             1.00,  '12 F75 — bottom LF x 1.10'),
    ('panels', 'durrock_retainer_lf',         1.80,  '12 F76 — both sides'),
    ('panels', 'form_rental_contact_ft',      0.65,  '12 F77 — off until a share is named'),

    -- Contract services.
    ('panels', 'concrete_pump_cy',           20.00,  '12 D99'),
    ('panels', 'panel_engineering_ea',       90.00,  '12 D100 — per panel type with any quantity'),
    ('panels', 'waterproofing_sf',            0,     '12 D101 — blank'),
    ('panels', 'saw_cutting_lf',              0,     '12 D102 — blank'),
    ('panels', 'haul_off_cy',                 6.00,  '12 F103')
ON CONFLICT (kind, key) DO NOTHING;

-- The price sheets: the kind's monetary rates on every job that has a sheet,
-- at the tab's values, so a panels section on an existing job prices the way
-- a new one would.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', a.kind, a.key, k.label, k.unit, a.kind || ' rates', a.value, a.value
  FROM estimates e
 CROSS JOIN assembly_rates a
  JOIN (VALUES
          ('labor_brick_ledge_lf',    'Brick ledge labor',        'LF'),
          ('labor_forming_sf',        'Forming labor',            'SF'),
          ('labor_place_finish_sf',   'Place & finish labor',     'SF'),
          ('labor_wreck_sf',          'Wreck forms labor',        'SF'),
          ('labor_rub_patch_sf',      'Rub & patch labor',        'SF'),
          ('labor_tie_steel_ton',     'Tie steel labor',          'TON'),
          ('labor_backfill_cy',       'Backfill labor',           'CY'),
          ('carton_forms_lf',         'Carton forms (beams)',     'LF'),
          ('durrock_retainer_lf',     'Durrock retainer',         'LF'),
          ('form_rental_contact_ft',  'Form rental',              'CONTACT FT'),
          ('concrete_pump_cy',        'Concrete pump',            'CY'),
          ('panel_engineering_ea',    'Panel engineering',        'EA'),
          ('waterproofing_sf',        'Waterproofing',            'SF'),
          ('saw_cutting_lf',          'Saw cutting',              'LF'),
          ('haul_off_cy',             'Haul off',                 'CY')
       ) AS k(key, label, unit) ON k.key = a.key
 WHERE a.kind = 'panels'
   AND EXISTS (SELECT 1 FROM estimate_prices p WHERE p.estimate_id = e.id)
ON CONFLICT DO NOTHING;
