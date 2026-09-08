-- 078_miscellaneous.sql
--
-- 13-Miscellaneous: the last tab, and a different animal from the twelve
-- before it — a priced LIBRARY of site items rather than a takeoff. Chad,
-- 2026-09-08: "ok, lets do miscellaneous" and, on the proposal, "Yes, make
-- those and then a way to add similar.. so have the 4 sections with the ones
-- shown as defaults, minus the quantities.. then a button for each section to
-- add another row". docs/specs/misc-spec.md.
--
-- One row is an ITEM: a typed unit SALE and a typed LABOR cost per unit, a
-- sub flag, and a shape the concrete and steel come from — four families on
-- the tab, each its own block of rows:
--
--     round   dia" x depth'        light pole bases, bollard bases, bike racks, pipe bollards
--     block   LF x W" x H"         elevator pits and waterproofing, monument base, transformer pads, gate track
--     slab    SF x thk"            trellis, gate column, fire pit, site wall and grill footings, curb, counters
--     box     L" x W" x D"         radon pits, stair treads, pour-back blockouts, ADA ramps
--
-- The rest of a row's cost — forms, supervision, equipment — is a typed
-- allowance with the tab's own formula as its default: forms as a share of
-- the sale plus dollars a unit (plus dollars a face SF on a pit, plus a share
-- of the concrete on the slabs), supervision as a share of labor, equipment as
-- dollars a unit plus a share of labor with a minimum. The margin is the
-- ANSWER on this tab — 1 - cost / sale, per row and for the section — and the
-- section's sale is the sum of the rows' typed sales, not cost x markup.
--
-- Nothing on any workbook in the folder is typed into this tab. The library
-- below is the tab's 22 named rows, seeded onto every new miscellaneous
-- section at no quantity; the four blank template rows (1305, 1324-1326) are
-- the "add another row" defaults, carried on the page.

CREATE TABLE IF NOT EXISTS misc_item_library (
    code               text PRIMARY KEY,           -- the tab's 1301..1323
    description        text NOT NULL,
    shape              text NOT NULL CHECK (shape IN ('round', 'block', 'slab', 'box')),
    unit               text NOT NULL DEFAULT 'EA',
    sort_order         integer NOT NULL DEFAULT 0,
    -- A row the tab prices with no concrete formula at all (the bike rack is
    -- an install, the waterproofing a service, the radon pit a sump).
    pours_concrete     boolean NOT NULL DEFAULT true,
    structural_mix     boolean NOT NULL DEFAULT false,   -- the tab's Q8 mix rather than its E8
    unit_sale          numeric(12, 2),
    labor_per_unit     numeric(12, 2) NOT NULL DEFAULT 0,
    subcontracted      boolean NOT NULL DEFAULT true,    -- the tab's F column, Y on every row
    dim_a              numeric(12, 3),
    dim_b              numeric(12, 3),
    dim_c              numeric(12, 3),
    concrete_waste     numeric(6, 4)  NOT NULL DEFAULT 0,
    steel_lb_per_cy    numeric(10, 3) NOT NULL DEFAULT 0,
    steel_lb_per_in_ft numeric(8, 4)  NOT NULL DEFAULT 0,   -- round bases: dia x depth x this
    steel_lb_per_unit  numeric(10, 3) NOT NULL DEFAULT 0,
    forms_pct_of_sale  numeric(6, 4)  NOT NULL DEFAULT 0,
    forms_per_unit     numeric(12, 2) NOT NULL DEFAULT 0,
    forms_per_face_sf  numeric(10, 4) NOT NULL DEFAULT 0,   -- blocks: L x H / 12 of face
    forms_pct_of_concrete numeric(6, 4) NOT NULL DEFAULT 0,
    super_pct_of_labor numeric(6, 4)  NOT NULL DEFAULT 0,
    equip_per_unit     numeric(12, 2) NOT NULL DEFAULT 0,
    equip_pct_of_labor numeric(6, 4)  NOT NULL DEFAULT 0,
    equip_min          numeric(12, 2) NOT NULL DEFAULT 0,
    notes              text
);

COMMENT ON TABLE misc_item_library IS
    'The 13-Miscellaneous tab''s 22 named items with their default sale, labor, dimensions '
    'and cost factors (sql/078). Copied onto a new miscellaneous section at no quantity.';

INSERT INTO misc_item_library
    (code, description, shape, unit, sort_order, pours_concrete, structural_mix, unit_sale, labor_per_unit,
     dim_a, dim_b, dim_c, concrete_waste, steel_lb_per_cy, steel_lb_per_in_ft, steel_lb_per_unit,
     forms_pct_of_sale, forms_per_unit, forms_per_face_sf, forms_pct_of_concrete,
     super_pct_of_labor, equip_per_unit, equip_pct_of_labor, equip_min, notes)
VALUES
    -- ------------------------------------------------- round: dia" x depth' --
    ('1301', 'Light Pole Bases',                 'round', 'EA', 10, true,  false, 1150.00, 350.00,
     24, 8, NULL, 0, 0, 0.95, 0,   0.10, 37.50, 0, 0,   0.20, 139.00, 0, 0,
     '13 row 10: steel dia x depth x 0.95; forms 10% of sale + 3 x $12.50; equipment 8 x depth + 75 a base'),
    ('1302', 'Bollard / Landscape Light Bases', 'round', 'EA', 20, true,  false,  350.00, 120.00,
     12, 6, NULL, 0, 0, 0.95, 0,   0.10, 37.50, 0, 0,   0.25,   8.00, 0, 0,
     '13 row 11'),
    ('1303', 'Bike Rack (Installation)',        'round', 'EA', 30, false, false,  300.00, 170.00,
     8, 2, NULL, 0, 0, 0, 0,      0.10,  1.00, 0, 0,   0.25,   8.00, 0, 0,
     '13 row 12: an install — the tab prices no concrete or steel on it'),
    ('1304', 'Pipe Bollards (Install Only)',    'round', 'EA', 40, true,  false,  150.00,  65.00,
     18, 3, NULL, 0, 0, 0, 0,      0, 0, 0, 0,          0.25,  20.00, 0, 0,
     '13 row 13: concrete only — no steel, no forms on the tab'),

    -- ------------------------------------------------- block: LF x W" x H" --
    ('1306', 'Elevator Pits',                   'block', 'EA', 10, true,  true,  18600.00, 6200.00,
     48, 16, 72, 0.15, 145, 0, 0,  0.15, 0, 4.25, 0,    0.10, 250.00, 0, 0,
     '13 row 17: the structural mix; a floor (L/4)^2 / 27 under the walls; forms 15% of sale + $4.25 a face SF'),
    ('1307', 'Elevator Water Proofing',         'block', 'EA', 20, false, true,   2600.00, 2000.00,
     20, 12, 24, 0.15, 0, 0, 0,    0, 0, 0, 0,          0.10,   0.00, 0, 0,
     '13 row 18: a service — the tab files its $2,000 a pit under forms and takes 10% supervision on it; labor here'),
    ('1308', 'Monument Base (15'' x 3'' x 36")', 'block', 'EA', 30, true,  false,  2800.00,  650.00,
     15, 36, 36, 0.15, 55, 0, 0,   0.20, 0, 0, 0,       0.30,  15.00, 0, 0,
     '13 row 19'),
    ('1309', 'Bldg Transformer Pad',            'block', 'LF', 40, true,  false,   500.00,  150.00,
     20, NULL, NULL, 0.15, 55, 0, 0, 0.10, 0, 0, 0,    0.30,  50.00, 0, 0,
     '13 row 20: the tab types a length and no section, so only the floor term carries concrete'),
    ('1310', 'Transformer Pads (Three Phase)',  'block', 'EA', 50, true,  false,  2500.00,  699.00,
     36, 12, 24, 0.15, 55, 0, 0,   0.10, 0, 0, 0,       0.30,  50.00, 0, 0,
     '13 row 21'),
    ('1311', 'Gate Track',                      'block', 'EA', 60, true,  false,    40.00,   16.00,
     1, 12, 12, 0.15, 55, 0, 10,   0.10, 0, 0, 0,       0.10,   3.00, 0, 0,
     '13 row 22: a foot of track; the tab adds L x 2.5 x 4 lb once, 10 lb a unit here'),

    -- ------------------------------------------------- slab: SF x thk" --
    ('1312', 'Trellis Ftgs',                    'slab', 'EA', 10, true,  false,   450.00,  150.00,
     9, 28, NULL, 0, 132.32, 0, 0, 0.10, 0, 0, 0,       0.15,   0.00, 0.15, 0,
     '13 row 25: steel 1% of 13,232 lb a CY; equipment = the supervision (15% of labor)'),
    ('1313', 'Gate Column Ftgs 3''x3''x2''',    'slab', 'EA', 20, true,  false,   550.00,  185.00,
     9, 24, NULL, 0, 132.32, 0, 0, 0.10, 0, 0, 0,       0.15,  55.00, 0, 0,
     '13 row 26'),
    ('1314', 'Fire Pit Footings',               'slab', 'EA', 30, true,  false,  1150.00,  360.00,
     36, 12, NULL, 0, 132.32, 0, 0, 0, 0, 0, 0.70,      0.15, 114.58, 0, 0,
     '13 row 27: forms 70% of the concrete; equipment = the steel dollars, $114.58 a footing at the tab''s prices'),
    ('1315', 'Site Wall Footing',               'slab', 'LF', 40, true,  false,    43.00,   16.00,
     2, 12, NULL, 0, 132.32, 0, 0, 0, 0, 0, 0.50,       0.10,   0.00, 0.10, 0,
     '13 row 28: 2 SF a foot; equipment = the supervision'),
    ('1316', 'Landscape Curb',                  'slab', 'LF', 50, true,  false,    38.00,   18.00,
     1, 12, NULL, 0, 132.32, 0, 0, 0, 0, 0, 0.50,       0.05,   3.18, 0, 0,
     '13 row 29: equipment = the steel dollars, $3.18 a foot at the tab''s prices'),
    ('1317', 'Call Box & Motor Pad Ftg',        'slab', 'EA', 60, true,  false,   350.00,  175.00,
     4, 18, NULL, 0, 132.32, 0, 0, 0, 0, 0, 0.50,       0.15,  19.10, 0, 0,
     '13 row 30: equipment = the steel dollars'),
    ('1318', 'Outdoor Prep Counter',            'slab', 'EA', 70, true,  false,  1400.00,  500.00,
     50, 12, NULL, 0, 132.32, 0, 0, 0, 0, 0, 0.50,      0.15, 159.15, 0, 0,
     '13 row 31: equipment = the steel dollars'),
    ('1319', 'Grill Footing (12" thick 369 sq ft)', 'slab', 'EA', 80, true, false, 11050.00, 3700.00,
     369, 12, NULL, 0, 132.32, 0, 0, 0, 0, 0, 0.70,     0.15, 1174.54, 0, 0,
     '13 row 32: equipment = the steel dollars'),

    -- ------------------------------------------------- box: L" x W" x D" --
    ('1320', 'Radon Pits',                      'box', 'EA', 10, false, false,   250.00,  150.00,
     24, 24, 5, 0.20, 0, 0, 0,     0, 25.00, 0, 0,       0.10,   0.00, 0, 0,
     '13 row 34: a sump — the tab prices no concrete on it; $25 of forms a pit'),
    ('1321', 'Stair Treads',                    'box', 'EA', 20, true,  false,   125.00,   57.00,
     60, 12, 12, 0.20, 0, 0, 0,    0, 8.00, 0, 0,        0.10,   0.00, 0.075, 0,
     '13 row 35: no steel; equipment 75% of the supervision'),
    ('1322', 'Pour Back Block Outs (3'' x 3'')', 'box', 'LF', 30, true,  false,   110.00,   50.00,
     36, 36, 6, 0.20, 66.625, 0, 0, 0, 5.00, 0, 0,      0.10,   0.00, 0, 0,
     '13 row 36: steel 0.5% of 13,325 lb a CY'),
    ('1323', 'ADA Ramps',                       'box', 'EA', 40, true,  false,   550.00,  350.00,
     60, 60, 4, 0.20, 211.7, 0, 0, 0, 0, 0, 0.50,       0, 0.00, 0, 0,
     '13 row 37: the tab''s steel is a ratio of the concrete dollars — 211.7 lb a CY at its $134 mix; forms half the concrete; no supervision or equipment typed');


CREATE TABLE IF NOT EXISTS misc_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections (id) ON DELETE CASCADE,

    code        text,
    description text,
    shape       text NOT NULL DEFAULT 'round' CHECK (shape IN ('round', 'block', 'slab', 'box')),
    unit        text NOT NULL DEFAULT 'EA',
    qty         numeric(12, 3) NOT NULL DEFAULT 0 CHECK (qty >= 0),

    -- The typed sale and the typed labor, the tab's H and J.
    unit_sale       numeric(12, 2),
    labor_per_unit  numeric(12, 2) NOT NULL DEFAULT 0,
    subcontracted   boolean NOT NULL DEFAULT true,

    pours_concrete  boolean NOT NULL DEFAULT true,
    mix_design_id   integer REFERENCES mix_designs (id) ON DELETE SET NULL,
    dim_a           numeric(12, 3),
    dim_b           numeric(12, 3),
    dim_c           numeric(12, 3),
    concrete_waste  numeric(6, 4)  NOT NULL DEFAULT 0,

    steel_lb_per_cy    numeric(10, 3) NOT NULL DEFAULT 0,
    steel_lb_per_in_ft numeric(8, 4)  NOT NULL DEFAULT 0,
    steel_lb_per_unit  numeric(10, 3) NOT NULL DEFAULT 0,

    forms_pct_of_sale     numeric(6, 4)  NOT NULL DEFAULT 0,
    forms_per_unit        numeric(12, 2) NOT NULL DEFAULT 0,
    forms_per_face_sf     numeric(10, 4) NOT NULL DEFAULT 0,
    forms_pct_of_concrete numeric(6, 4)  NOT NULL DEFAULT 0,
    super_pct_of_labor    numeric(6, 4)  NOT NULL DEFAULT 0,
    equip_per_unit        numeric(12, 2) NOT NULL DEFAULT 0,
    equip_pct_of_labor    numeric(6, 4)  NOT NULL DEFAULT 0,
    equip_min             numeric(12, 2) NOT NULL DEFAULT 0,

    notes       text,
    sort_order  integer NOT NULL DEFAULT 0,

    -- Quantities, from the shape (refresh_misc_item_calcs).
    calc_concrete_cy    numeric(14, 4),
    calc_steel_lb       numeric(14, 3),
    calc_face_sf        numeric(14, 3),
    -- The typed sale, x qty.
    calc_sale           numeric(14, 2),
    -- The six pieces of the cost, priced at cost time (costing._misc_units).
    calc_concrete_cost  numeric(14, 2),
    calc_steel_cost     numeric(14, 2),
    calc_forms_cost     numeric(14, 2),
    calc_labor_cost     numeric(14, 2),
    calc_super_cost     numeric(14, 2),
    calc_equip_cost     numeric(14, 2),
    calc_margin         numeric(8, 4),          -- 1 - cost / sale, the tab's Z

    calc_direct_cost    numeric(14, 2),
    calc_allocated_cost numeric(14, 2),
    calc_equip_fuel     numeric(14, 2),
    calc_tax            numeric(14, 2),
    calc_cost           numeric(14, 2),
    calc_cost_per_unit  numeric(14, 4),         -- per item
    calc_sale_per_unit  numeric(14, 4),

    updated_by  uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS misc_items_section_idx        ON misc_items (section_id);
CREATE INDEX IF NOT EXISTS misc_items_mix_design_id_idx  ON misc_items (mix_design_id);
CREATE INDEX IF NOT EXISTS misc_items_updated_by_idx     ON misc_items (updated_by);

COMMENT ON TABLE misc_items IS
    'One priced site item on a miscellaneous section (sql/078): a typed unit sale, a typed labor '
    'cost, a shape the concrete and steel come from, and the rest of the cost as typed allowances. '
    'The section''s sale is the sum of the rows'' sales; the margin is the answer.';
COMMENT ON COLUMN misc_items.calc_margin IS
    '1 - cost / sale for the row — the tab''s Z column. NULL with no sale.';
