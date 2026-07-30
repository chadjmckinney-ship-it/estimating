-- Materials master list from Pricing tab (Whitecap / unit-rate catalog)
-- Source: workbooks/Downloads/Updated Estimate Worksheet.xlsm → sheet "Pricing"
--   - Cols M–O: Lumber & accessories (main list)
--   - Cols A–E: Steel, mesh, PT, sand/rock unit rates
-- Apply: psql -d estimating -f sql/002_materials.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- materials: company-wide catalog (unit costs are defaults; override per job later)
-- ---------------------------------------------------------------------------
CREATE TABLE materials (
    id              serial PRIMARY KEY,
    code            text UNIQUE,                 -- cost code (optional, TBD mapping)
    name            text NOT NULL,
    category        text NOT NULL
                    CHECK (category IN (
                        'lumber',
                        'form_accessories',
                        'structural_accessories',
                        'site_accessories',
                        'vapor_barrier',
                        'foam',
                        'steel',
                        'mesh',
                        'pt',
                        'aggregate',
                        'chemical',
                        'other'
                    )),
    unit            text NOT NULL,               -- LF, SF, LB, EA, BOX, BAG, ROLL, DRUM, SHEET, BUNDLE, CF, CY
    unit_cost       numeric(12, 4),              -- default unit price
    unit_note       text,                        -- pack size / size note (e.g. 50/BOX, 2" x 4 x 8)
    description     text,
    supplier_ref    text,                        -- e.g. Whitecap
    price_as_of     date,
    is_active       boolean NOT NULL DEFAULT true,
    sort_order      integer NOT NULL DEFAULT 0,
    source_sheet    text DEFAULT 'Pricing',
    source_row      integer,                     -- Excel row for traceability
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name, unit)
);

CREATE INDEX materials_category_idx ON materials (category);
CREATE INDEX materials_name_idx ON materials (name);

COMMENT ON TABLE materials IS
    'Master material / unit-price catalog from the estimate workbook Pricing tab';
COMMENT ON COLUMN materials.unit_cost IS
    'Default unit cost; job-level overrides can come later via estimate_material_prices';

-- ---------------------------------------------------------------------------
-- Seed: Lumber & accessories (Pricing M–O, Whitecap update 5/12/2025)
-- ---------------------------------------------------------------------------
INSERT INTO materials
    (name, category, unit, unit_cost, unit_note, supplier_ref, price_as_of, sort_order, source_row)
VALUES
    -- Lumber
    ('2 X 4  X 16''',                    'lumber',                 'LF',     0.5625,  NULL,              'Whitecap', '2025-05-12',  10,  3),
    ('2 X 6 X 16''',                     'lumber',                 'LF',     0.65625, NULL,              'Whitecap', '2025-05-12',  20,  4),
    ('2 X 8 X 16''',                     'lumber',                 'LF',     1.0000,  NULL,              'Whitecap', '2025-05-12',  30,  5),
    ('2 X 10 X 16''',                    'lumber',                 'LF',     1.2500,  NULL,              'Whitecap', '2025-05-12',  40,  6),
    ('3/4 " FORMING PLY',                'lumber',                 'SHEET', 50.0000,  NULL,              'Whitecap', '2025-05-12',  50,  7),
    ('MASONITE SIDING',                  'lumber',                 'SHEET', 19.0000,  NULL,              'Whitecap', '2025-05-12',  60,  8),
    ('1 X 1 TACT STRIP',                 'lumber',                 'LF',     0.1500,  NULL,              'Whitecap', '2025-05-12',  70,  9),
    ('1 X 4 RED WOOD',                   'lumber',                 'LF',     1.0000,  NULL,              'Whitecap', '2025-05-12',  80, 10),
    ('1 X 6 RED WOOD',                   'lumber',                 'LF',     1.2500,  NULL,              'Whitecap', '2025-05-12',  90, 11),
    ('1 X 8 RED WOOD',                   'lumber',                 'LF',     0.9000,  NULL,              'Whitecap', '2025-05-12', 100, 12),
    ('ACCESSORIES',                      'form_accessories',       'LB',     0.0400,  NULL,              'Whitecap', '2025-05-12', 110, 13),
    ('2 x 2 x 30 Stakes',                'lumber',                 'BUNDLE',18.0000,  NULL,              'Whitecap', '2025-05-12', 120, 14),
    ('16p NAILS DUPLEX',                 'lumber',                 'BOX',   42.0000,  NULL,              'Whitecap', '2025-05-12', 130, 15),
    ('8p DUPLEX',                        'lumber',                 'BOX',   42.0000,  NULL,              'Whitecap', '2025-05-12', 140, 16),
    ('6p NAILS',                         'lumber',                 'BOX',   42.0000,  NULL,              'Whitecap', '2025-05-12', 150, 17),
    ('KEYWAY',                           'lumber',                 'LF',     0.7800,  NULL,              'Whitecap', '2025-05-12', 160, 18),
    ('CHAMFER',                          'lumber',                 'LF',     0.1600,  NULL,              'Whitecap', '2025-05-12', 170, 19),
    ('WALL TIES',                        'lumber',                 'BOX',   45.0000,  '50/BOX',          'Whitecap', '2025-05-12', 180, 20),
    ('1 X 2 X 18" STAKES',               'lumber',                 'BUNDLE', 8.0000,  NULL,              'Whitecap', '2025-05-12', 190, 21),

    -- Structural accessories
    ('METAL CHAIRS 2.5"',                'structural_accessories', 'BAG',   45.0000,  'BAG/500',         'Whitecap', '2025-05-12', 200, 23),
    ('LIFT INSERT',                      'structural_accessories', 'EA',    12.0000,  NULL,              'Whitecap', '2025-05-12', 210, 24),
    ('CAMLOCKS',                         'structural_accessories', 'EA',     0.2500,  NULL,              'Whitecap', '2025-05-12', 220, 25),
    ('TURNBUCKLES',                      'structural_accessories', 'EA',     0.7500,  NULL,              'Whitecap', '2025-05-12', 230, 26),
    ('PATCH MATERIAL',                   'structural_accessories', 'BAG',   15.0000,  NULL,              'Whitecap', '2025-05-12', 240, 27),
    ('PIER SLEDS',                       'structural_accessories', 'EA',     1.7000,  NULL,              'Whitecap', '2025-05-12', 250, 28),
    ('PIER BOOTS',                       'structural_accessories', 'EA',     2.7000,  NULL,              'Whitecap', '2025-05-12', 260, 29),
    ('SLAB CHAIRS',                      'structural_accessories', 'BAG',   27.0000,  NULL,              'Whitecap', '2025-05-12', 270, 30),
    ('POLSTERS',                         'structural_accessories', 'LF',     1.2500,  NULL,              'Whitecap', '2025-05-12', 280, 31),  -- workbook spelling
    ('BRACE INSERTS',                    'structural_accessories', 'EA',     8.0000,  NULL,              'Whitecap', '2025-05-12', 290, 32),
    ('ANCHOR BOLTS',                     'structural_accessories', 'BOX',   25.5000,  NULL,              'Whitecap', '2025-05-12', 300, 33),
    ('TIE WIRE',                         'structural_accessories', 'ROLL',   4.0000,  NULL,              'Whitecap', '2025-05-12', 310, 34),

    -- Site accessories / chemicals
    ('2-1/4 PAVING CHAIRS',              'site_accessories',       'BAG',   20.0000,  NULL,              'Whitecap', '2025-05-12', 320, 36),
    ('3-1/4 PAVING CHAIRS',              'site_accessories',       'BAG',   35.0000,  NULL,              'Whitecap', '2025-05-12', 330, 37),
    ('ANCHOR BOLTS 8"x1/2" (50/BX)',     'site_accessories',       'BOX',   20.0000,  '50/BX',           'Whitecap', '2025-05-12', 340, 38),
    ('SPEED DOWEL INSERT w/ BASE',       'site_accessories',       'EA',     1.0000,  NULL,              'Whitecap', '2025-05-12', 350, 39),
    ('SNAP TIES',                        'site_accessories',       'BOX',   40.0000,  NULL,              'Whitecap', '2025-05-12', 360, 40),
    ('POLY 10 mill',                     'site_accessories',       'ROLL', 100.0000,  NULL,              'Whitecap', '2025-05-12', 370, 41),
    ('SLAB CURE',                        'chemical',               'DRUM', 540.0000,  NULL,              'Whitecap', '2025-05-12', 380, 42),
    ('FORM RELEASE',                     'chemical',               'DRUM', 542.0000,  NULL,              'Whitecap', '2025-05-12', 390, 43),
    ('BOND BREAKER',                     'chemical',               'DRUM', 635.0000,  NULL,              'Whitecap', '2025-05-12', 400, 44),

    -- Poly vapor barrier
    ('6 mil 20 x 100',                   'vapor_barrier',          'ROLL',  60.0000,  NULL,              'Whitecap', '2025-05-12', 410, 46),
    ('6 mil 32 x 100',                   'vapor_barrier',          'ROLL',  80.0000,  NULL,              'Whitecap', '2025-05-12', 420, 47),
    ('10 mil 20 x 100',                  'vapor_barrier',          'ROLL', 120.0000,  NULL,              'Whitecap', '2025-05-12', 430, 48),
    ('STEGO WRAP 10 mil. 20 x 150',      'vapor_barrier',          'ROLL', 400.0000,  NULL,              'Whitecap', '2025-05-12', 440, 49),
    ('RW Medows 15 mil VAPOR MAT',       'vapor_barrier',          'ROLL', 355.0000,  NULL,              'Whitecap', '2025-05-12', 450, 50),

    -- Foam fill (two units in workbook)
    ('FOAM FILL VOID',                   'foam',                   'EA',    22.7600,  '2" x 4 x 8',      'Whitecap', '2025-05-12', 460, 52),
    ('FOAM FILL VOID',                   'foam',                   'CF',     1.6500,  NULL,              'Whitecap', '2025-05-12', 470, 53),

    -- Steel / mesh / PT / aggregate (Pricing left column unit rates)
    ('SAND DELIVERED PER TON',           'aggregate',              'CY',    25.0000,  NULL,              NULL,       '2025-05-12', 1000, 18),
    ('ROCK DELEVERED PER TON',           'aggregate',              'CY',    40.0000,  NULL,              NULL,       '2025-05-12', 1010, 19),  -- workbook spelling
    ('REBAR PIERS',                      'steel',                  'LB',     0.7000,  NULL,              NULL,       '2025-05-12', 1020, 21),
    ('REBAR GRADE BEAM',                 'steel',                  'LB',     0.7000,  NULL,              NULL,       '2025-05-12', 1030, 22),
    ('REBAR PAVING',                     'steel',                  'LB',     0.6500,  NULL,              NULL,       '2025-05-12', 1040, 23),
    ('DOWEL SPACING / 3/4" & CAP',       'steel',                  'EA',     2.0000,  NULL,              NULL,       '2025-05-12', 1050, 24),
    ('WIRE MESH 10 GAGE',                'mesh',                   'SF',     0.4000,  '10 GAGE',         NULL,       '2025-05-12', 1060, 25),
    ('WIRE MESH 8 GAGE',                 'mesh',                   'SF',     0.4000,  '8 GAGE',          NULL,       '2025-05-12', 1070, 26),
    ('WIRE MESH 6 GAGE',                 'mesh',                   'SF',     0.4000,  '6 GAGE',          NULL,       '2025-05-12', 1080, 27),
    ('POST TENSION CABLES',              'pt',                     'SF',     0.6500,  NULL,              NULL,       '2025-05-12', 1090, 28),
    ('1/2" SMOOTH DOWELS & CAP',         'steel',                  'EA',     1.7500,  NULL,              NULL,       '2025-05-12', 1100, 29);

-- Optional: point mono_slab mix_design at materials later; keep mix_designs for now.

COMMIT;
