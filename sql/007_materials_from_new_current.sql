-- Sync materials from "New Current Worksheet.xlsm" Pricing tab (cols P–R + left rates)
-- Source note on sheet: lumber price update 9-1-21; unit cost = Pricing Q column
-- Apply: psql -d estimating -f sql/007_materials_from_new_current.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- Price updates (matched items)
-- ---------------------------------------------------------------------------
UPDATE materials SET unit_cost = 0.8594, price_as_of = '2021-09-01', supplier_ref = coalesce(supplier_ref, '84 Lumber'),
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 4, updated_at = now()
WHERE name = '2 X 4  X 16''' AND unit = 'LF';

UPDATE materials SET unit_cost = 1.4453, price_as_of = '2021-09-01', supplier_ref = coalesce(supplier_ref, '84 Lumber'),
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 5, updated_at = now()
WHERE name = '2 X 6 X 16''' AND unit = 'LF';

UPDATE materials SET unit_cost = 1.1719, price_as_of = '2021-09-01', supplier_ref = coalesce(supplier_ref, '84 Lumber'),
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 6, updated_at = now()
WHERE name = '2 X 8 X 16''' AND unit = 'LF';

UPDATE materials SET unit_cost = 1.0938, price_as_of = '2021-09-01', supplier_ref = coalesce(supplier_ref, '84 Lumber'),
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 7, updated_at = now()
WHERE name = '2 X 10 X 16''' AND unit = 'LF';

UPDATE materials SET unit_cost = 74.7500, price_as_of = '2021-09-01', supplier_ref = coalesce(supplier_ref, '84 Lumber'),
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 8, updated_at = now()
WHERE name = '3/4 " FORMING PLY' AND unit = 'SHEET';

UPDATE materials SET unit_cost = 20.0000, price_as_of = '2021-09-01', supplier_ref = coalesce(supplier_ref, '84 Lumber'),
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 9, updated_at = now()
WHERE name = 'MASONITE SIDING';

UPDATE materials SET unit_cost = 0.7088, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 10, updated_at = now()
WHERE name = '1 X 1 TACT STRIP';

UPDATE materials SET unit_cost = 0.7772, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 11, updated_at = now()
WHERE name = '1 X 4 RED WOOD';

UPDATE materials SET unit_cost = 1.0631, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 12, updated_at = now()
WHERE name = '1 X 6 RED WOOD';

UPDATE materials SET unit_cost = 1.4944, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 13, updated_at = now()
WHERE name = '1 X 8 RED WOOD';

UPDATE materials SET unit_cost = 24.0000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 15, updated_at = now()
WHERE name ILIKE '2 x 2 x 30 Stakes%';

UPDATE materials SET unit_cost = 68.2000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 16, updated_at = now()
WHERE name = '16p NAILS DUPLEX';

UPDATE materials SET unit_cost = 68.2000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 17, updated_at = now()
WHERE name = '8p DUPLEX';

UPDATE materials SET unit_cost = 68.2000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 18, updated_at = now()
WHERE name = '6p NAILS';

UPDATE materials SET unit_cost = 0.9500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 19, updated_at = now()
WHERE name = 'KEYWAY';

UPDATE materials SET unit_cost = 0.2500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 20, updated_at = now()
WHERE name = 'CHAMFER';

UPDATE materials SET unit_cost = 0.4500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 26, updated_at = now()
WHERE name = 'CAMLOCKS';

UPDATE materials SET unit_cost = 45.0000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 28, updated_at = now()
WHERE name = 'PATCH MATERIAL';

UPDATE materials SET unit_cost = 2.2500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 29, updated_at = now()
WHERE name = 'PIER SLEDS';

UPDATE materials SET unit_cost = 3.0000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 30, updated_at = now()
WHERE name = 'PIER BOOTS';

UPDATE materials SET unit_cost = 37.8000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 36, updated_at = now()
WHERE name = 'TIE WIRE';

UPDATE materials SET unit_cost = 23.9250, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 38, updated_at = now()
WHERE name = '2-1/4 PAVING CHAIRS';

UPDATE materials SET unit_cost = 27.0000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 39, updated_at = now()
WHERE name = '3-1/4 PAVING CHAIRS';

UPDATE materials SET unit_cost = 52.2000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 40, updated_at = now()
WHERE name = 'ANCHOR BOLTS 8"x1/2" (50/BX)';

UPDATE materials SET unit_cost = 1.5000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 41, updated_at = now()
WHERE name = 'SPEED DOWEL INSERT w/ BASE';

UPDATE materials SET unit_cost = 45.0000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 42, updated_at = now()
WHERE name = 'SNAP TIES';

UPDATE materials SET unit_cost = 567.5000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 44, updated_at = now()
WHERE name = 'SLAB CURE';

UPDATE materials SET unit_cost = 66.0000, price_as_of = '2022-03-11', source_sheet = 'Pricing (New Current Worksheet)', source_row = 53, updated_at = now()
WHERE name = '6 mil 20 x 100';

UPDATE materials SET unit_cost = 82.5000, price_as_of = '2022-03-11', source_sheet = 'Pricing (New Current Worksheet)', source_row = 54, updated_at = now()
WHERE name = '6 mil 32 x 100';

UPDATE materials SET unit_cost = 110.0000, price_as_of = '2022-03-11', source_sheet = 'Pricing (New Current Worksheet)', source_row = 55, updated_at = now()
WHERE name = '10 mil 20 x 100';

UPDATE materials SET unit_cost = 45.0000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 20, updated_at = now()
WHERE name = 'ROCK DELEVERED PER TON';

UPDATE materials SET unit_cost = 0.5500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 23, updated_at = now()
WHERE name = 'REBAR GRADE BEAM';

UPDATE materials SET unit_cost = 0.5000, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 24, updated_at = now()
WHERE name = 'REBAR PAVING';

UPDATE materials SET unit_cost = 1.4500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 25, updated_at = now()
WHERE name = 'DOWEL SPACING / 3/4" & CAP';

UPDATE materials SET unit_cost = 0.4581, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 27, updated_at = now()
WHERE name = 'WIRE MESH 6 GAGE';

UPDATE materials SET unit_cost = 1.0500, price_as_of = '2021-09-01', source_sheet = 'Pricing (New Current Worksheet)', source_row = 29, updated_at = now()
WHERE name = 'POST TENSION CABLES';

UPDATE materials SET unit = 'BAG', unit_note = 'BAG/500', source_sheet = 'Pricing (New Current Worksheet)', source_row = 24, updated_at = now()
WHERE name = 'METAL CHAIRS 2.5"';

UPDATE materials SET unit = 'EA', unit_note = '2" x 4 x 8', unit_cost = 22.7600,
    source_sheet = 'Pricing (New Current Worksheet)', source_row = 60, updated_at = now()
WHERE name = 'FOAM FILL VOID' AND unit = 'EA';

-- Rename / retarget steel & poly
UPDATE materials SET
    name = 'REBAR PIERS / PT slabs',
    unit_cost = 0.6000,
    price_as_of = '2021-09-01',
    source_sheet = 'Pricing (New Current Worksheet)',
    source_row = 22,
    updated_at = now()
WHERE name = 'REBAR PIERS' AND unit = 'LB';

UPDATE materials SET
    name = 'POLY 10 mil 20 x 100 Black',
    unit_cost = 105.0000,
    price_as_of = '2021-09-01',
    source_sheet = 'Pricing (New Current Worksheet)',
    source_row = 43,
    updated_at = now()
WHERE name = 'POLY 10 mill' AND unit = 'ROLL';

-- Wire mesh: workbook has 10, 6, 5 gage (not 8)
UPDATE materials SET
    name = 'WIRE MESH 5 GAGE',
    unit_note = '5 GAGE',
    unit_cost = 0.8625,
    price_as_of = '2021-09-01',
    source_sheet = 'Pricing (New Current Worksheet)',
    source_row = 28,
    updated_at = now()
WHERE name = 'WIRE MESH 8 GAGE';

-- Smooth dowels: replace generic with 1/2"x24" as primary left-col rate was 1.00 each;
-- keep generic as inactive, add size variants
UPDATE materials SET
    is_active = false,
    description = coalesce(description || ' | ', '') || 'Superseded by size-specific smooth dowels from New Current Worksheet',
    updated_at = now()
WHERE name = '1/2" SMOOTH DOWELS & CAP';

-- Old vapor products replaced by expanded Stego/Yellow Guard list
UPDATE materials SET
    is_active = false,
    description = coalesce(description || ' | ', '') || 'Not on New Current Worksheet Pricing; superseded by expanded vapor list',
    updated_at = now()
WHERE name IN (
    'STEGO WRAP 10 mil. 20 x 150',
    'RW Medows 15 mil VAPOR MAT'
);

-- Generic ANCHOR BOLTS superseded by Galv sizes
UPDATE materials SET
    is_active = false,
    description = coalesce(description || ' | ', '') || 'Superseded by ANCHOR BOLTS 1/2" x 8" Galv / 10" Galv on New Current Worksheet',
    updated_at = now()
WHERE name = 'ANCHOR BOLTS' AND unit = 'BOX';

-- ---------------------------------------------------------------------------
-- New materials from New Current Worksheet
-- ---------------------------------------------------------------------------
INSERT INTO materials (name, category, unit, unit_cost, unit_note, supplier_ref, price_as_of, sort_order, source_sheet, source_row)
VALUES
    ('ANCHOR BOLTS 1/2" x 8" Galv', 'structural_accessories', 'BOX', 45.2400, NULL, NULL, '2021-09-01', 305, 'Pricing (New Current Worksheet)', 34),
    ('Anchor Bolts 1/2" x 10" Galv.', 'structural_accessories', 'BOX', 52.2600, NULL, NULL, '2021-09-01', 306, 'Pricing (New Current Worksheet)', 35),
    ('1/2" x 24" smooth dowels', 'steel', 'EA', 1.9950, NULL, NULL, '2021-09-01', 1110, 'Pricing (New Current Worksheet)', 47),
    ('1/2" x 30" smooth dowels', 'steel', 'EA', 2.2500, NULL, NULL, '2021-09-01', 1111, 'Pricing (New Current Worksheet)', 48),
    ('5/8" x 24" smooth dowels', 'steel', 'EA', 3.1200, NULL, NULL, '2021-09-01', 1112, 'Pricing (New Current Worksheet)', 49),
    ('3/4" x 24" smooth dowels', 'steel', 'EA', 4.9950, NULL, NULL, '2021-09-01', 1113, 'Pricing (New Current Worksheet)', 50),
    ('10 mil. Stego Wrap 14 x 210', 'vapor_barrier', 'ROLL', 370.0000, NULL, 'Stego', '2022-03-11', 460, 'Pricing (New Current Worksheet)', 56),
    ('15 mil Stego Wrap 14'' x 140''', 'vapor_barrier', 'ROLL', 370.0000, NULL, 'Stego', '2022-03-11', 461, 'Pricing (New Current Worksheet)', 57),
    ('10 mil Yellow Guard 14'' x 210''', 'vapor_barrier', 'ROLL', 310.0000, NULL, 'Yellow Guard', '2022-03-11', 462, 'Pricing (New Current Worksheet)', 58),
    ('15 Mil Yellow Guard 14''x210', 'vapor_barrier', 'ROLL', 310.0000, NULL, 'Yellow Guard', '2022-03-11', 463, 'Pricing (New Current Worksheet)', 59),
    ('Stego Tape', 'vapor_barrier', 'EA', 49.5000, NULL, 'Stego', '2022-03-11', 470, 'Pricing (New Current Worksheet)', 62),
    ('Yellow Guard Tape', 'vapor_barrier', 'EA', 23.6500, NULL, 'Yellow Guard', '2022-03-11', 471, 'Pricing (New Current Worksheet)', 63),
    ('Perminator 15 mil 12'' x 200''', 'vapor_barrier', 'ROLL', 432.7500, NULL, NULL, '2022-03-11', 472, 'Pricing (New Current Worksheet)', 64),
    ('Yellow Guard 15 mil 14'' x 140''', 'vapor_barrier', 'ROLL', 356.6725, NULL, 'Yellow Guard', '2022-03-11', 473, 'Pricing (New Current Worksheet)', 66),
    ('Tape', 'vapor_barrier', 'EA', 17.2500, NULL, NULL, '2022-03-11', 474, 'Pricing (New Current Worksheet)', 67),
    ('Raven 15 x 200  10 mil', 'vapor_barrier', 'ROLL', 305.0000, NULL, 'Raven', '2022-03-11', 475, 'Pricing (New Current Worksheet)', 68),
    ('R.W Medows  12'' x 200', 'vapor_barrier', 'ROLL', 249.6000, NULL, 'RW Meadows', '2022-03-11', 476, 'Pricing (New Current Worksheet)', 69)
ON CONFLICT (name, unit) DO UPDATE SET
    unit_cost = EXCLUDED.unit_cost,
    unit_note = EXCLUDED.unit_note,
    price_as_of = EXCLUDED.price_as_of,
    supplier_ref = COALESCE(EXCLUDED.supplier_ref, materials.supplier_ref),
    source_sheet = EXCLUDED.source_sheet,
    source_row = EXCLUDED.source_row,
    is_active = true,
    updated_at = now();

-- Left-column generic 1/2" smooth dowels & cap still on Pricing at $1/EA
INSERT INTO materials (name, category, unit, unit_cost, unit_note, price_as_of, sort_order, source_sheet, source_row, is_active)
VALUES ('1/2" SMOOTH DOWELS & CAP', 'steel', 'EA', 1.0000, NULL, '2021-09-01', 1105, 'Pricing (New Current Worksheet)', 30, true)
ON CONFLICT (name, unit) DO UPDATE SET
    unit_cost = 1.0000,
    is_active = true,
    price_as_of = '2021-09-01',
    source_sheet = 'Pricing (New Current Worksheet)',
    source_row = 30,
    updated_at = now();

COMMIT;
