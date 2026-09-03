-- 036: paving
--
-- Phase 3. Everything here is read off 10-PAVING in the LBJ workbook; the full
-- derivation, cell by cell, is in claude/paving-spec.md. Acceptance is
-- $1,327,183.47 on 272,703 SF at 8.25% tax and 18% markup, less the four
-- named workbook bugs the app deliberately does not reproduce (see the bottom
-- of this file).
--
-- A paving area IS a pour. It has SF, a thickness, sand under it, a mix, and a
-- bar mat — the same six fields a mono-slab pour has, computed the same way.
-- So paving areas live in mono_slabs rather than a table of their own, and the
-- allocation, costing and rollup machinery works unchanged. What paving adds
-- is six drivers the building slab has no use for, added here.
--
-- The structural difference is not in this file: paving's forming is driven by
-- CURB LF where the slab sheet uses perimeter, and that lives in the paving
-- line sets in app/services/. What lives here is the data those line sets read.

BEGIN;

-- ------------------------------------------------------- pour drivers ------

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS curb_lf            numeric(14, 3),
    ADD COLUMN IF NOT EXISTS thick_edge_lf      numeric(14, 3),
    ADD COLUMN IF NOT EXISTS demo_lf            numeric(14, 3),
    ADD COLUMN IF NOT EXISTS slip_form          boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS traffic_control    boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS paving_add_per_sf  numeric(12, 4),
    ADD COLUMN IF NOT EXISTS mesh_gauge         smallint,
    ADD COLUMN IF NOT EXISTS calc_edge_concrete_cy numeric(14, 4);

COMMENT ON COLUMN mono_slabs.curb_lf IS
    'Paving: LF of curb (sheet column I). Drives this pour''s curb concrete '
    '(LF / 108 = 0.25 CF per foot), the section''s forming package, and the '
    'CURB labor line. Paving forms off curb, not perimeter.';
COMMENT ON COLUMN mono_slabs.thick_edge_lf IS
    'Paving: LF of thickened edge (sheet column K). Adds LF x 1.5 x 0.18 / 27 CY.';
COMMENT ON COLUMN mono_slabs.demo_lf IS
    'Paving: LF of demolition on this area (sheet column H), priced per LF.';
COMMENT ON COLUMN mono_slabs.slip_form IS
    'Paving: this area is slip formed (sheet column B), priced per SF.';
COMMENT ON COLUMN mono_slabs.traffic_control IS
    'Paving: this area needs traffic control (sheet column G). The barricade '
    'months are entered on the section; this marks which areas carry them.';
COMMENT ON COLUMN mono_slabs.paving_add_per_sf IS
    'Paving: $/SF adder for this area (sheet column F). Feeds the LABOR '
    'ADJUSTMENT line as SF x rate — column BA on the sheet, which is where it '
    'lands. It is a labor adder, not a material one.';
COMMENT ON COLUMN mono_slabs.mesh_gauge IS
    'Paving: mesh gauge call-out (sheet column O). Recorded with the takeoff; '
    'mesh is priced from wire_mesh + the catalog, as on the slab sheet.';
COMMENT ON COLUMN mono_slabs.calc_edge_concrete_cy IS
    'Curb + thickened-edge concrete: (curb_lf / 108 + thick_edge_lf x 1.5 x '
    '0.18 / 27) x (1 + waste_concrete). Kept apart from calc_slab_concrete_cy '
    'so the flat plane still means the flat plane on every assembly.';

ALTER TABLE mono_slabs
    ADD CONSTRAINT mono_slabs_curb_lf_nonneg
        CHECK (curb_lf IS NULL OR curb_lf >= 0),
    ADD CONSTRAINT mono_slabs_thick_edge_lf_nonneg
        CHECK (thick_edge_lf IS NULL OR thick_edge_lf >= 0),
    ADD CONSTRAINT mono_slabs_demo_lf_nonneg
        CHECK (demo_lf IS NULL OR demo_lf >= 0);

-- ------------------------------------------------ taxable takeoff lines ----
--
-- Until now every forming line was taxed, because on the slab sheet every one
-- of them is. The paving sheet has lines that are not — some rightly (concrete
-- haul-off is a service), most because the author typed `=T*R` where the row
-- above says `=T*R*(1+tax)`. The flag lets a line set say which it is, and
-- lets the four bugs be named instead of silently reproduced.

ALTER TABLE estimate_forming_lines
    ADD COLUMN IF NOT EXISTS taxable boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN estimate_forming_lines.taxable IS
    'False for genuine services sitting in the materials block (concrete '
    'haul-off). Sales tax is applied at cost time, so this decides whether '
    'this line''s share of the section is taxed.';

-- ----------------------------------------------- paving assembly rates -----
--
-- A row here means "this assembly DIFFERS" (sql/035). Everything paving shares
-- with the company defaults is deliberately absent so a settings change still
-- reaches it.

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    -- The paving sheet forms 100% of its curb (R47 = 1) against the slab
    -- sheet's 50% of perimeter. Left at the company default the whole lumber
    -- package would come out half size.
    ('paving', 'form_percent',              1.00,  'Sheet 10-PAVING R47'),

    -- Waste. Each sheet carries its own; paving's are J47 / J54 / J57.
    ('paving', 'waste_concrete',            0.06,  'Sheet 10-PAVING J47'),
    ('paving', 'waste_sand',                0.06,  'Sheet 10-PAVING J57'),
    ('paving', 'waste_rebar',               0.10,  'Sheet 10-PAVING J54'),

    -- Paving carries no support steel. The building slab's 0.1 lb/SF is the #3
    -- that holds cables and mat up over a beam cage; a paving mat sits on
    -- chairs, which are already a line of their own. Left at the company
    -- default it would have added 27,270 lb of steel nobody buys.
    ('paving', 'support_rebar_lb_per_sf',   0.00,  'No support steel on 10-PAVING'),

    -- No vapor barrier line exists on the paving sheet. 0 means the pour
    -- computes no poly SF at all, rather than computing it and pricing it.
    ('paving', 'vapor_barrier_enabled',     0,     'No poly line on 10-PAVING'),

    -- A price that differs by assembly. The catalog is still where prices
    -- live; a row here says this assembly buys the same thing at a different
    -- number, the same way it forms at a different number.
    --
    -- Steel deliberately gets NO row: the catalog already carries a REBAR
    -- PAVING item, which is the right place for it, and costing now reaches
    -- for that on a paving section. Worth knowing that the catalog says $0.50
    -- where the sheet types $0.55 — see claude/paving-spec.md.
    ('paving', 'accessories_unit_cost',     0.02,  'Sheet 10-PAVING T80 (catalog: 0.04)'),

    -- Contract services priced on the paving sheet.
    ('paving', 'joint_construction_lf',     1.60,  'HOT POUR JOINT SEALANT, D82'),
    ('paving', 'joint_control_lf',          0.65,  'HOT POUR CTRL JOINT SEALANT, D83'),
    ('paving', 'joint_soft_cut_lf',         0.45,  'SOFT CUT, D84 (Pricing!E71)'),
    ('paving', 'stamping_sf',               2.50,  'STAMPING, D86'),
    ('paving', 'demo_lf',                   6.00,  'DEMO, D87'),
    ('paving', 'slip_form_sf',              5.00,  'SLIP FORMING, D88'),
    ('paving', 'barricades_month',       3500.00,  'BARRICADES, F80'),
    ('paving', 'form_rental_contact_ft',    0.65,  'FORM RENTAL, F59'),
    ('paving', 'rock_cy',                  15.00,  'TOTAL ROCK, F58'),
    ('paving', 'concrete_pump_cy',          0.00,  'CONCRETE PUMP, D85 — not pumped'),

    -- Equipment. Paving runs a Bob Cat, a light tower and a vault; the vault
    -- is $15/day here against the company $25.
    ('paving', 'equip_vault_day_rate',     15.00,  'Sheet 10-PAVING F79'),
    ('paving', 'equip_bobcat_day_rate',   325.00,  'Sheet 10-PAVING F76 (Pricing!D35)'),
    ('paving', 'equip_light_tower_day_rate', 100.00, 'Sheet 10-PAVING F78 (Pricing!D39)'),

    -- Paving-only labor lines, priced at 0 until a job needs them — the sheet
    -- carries both rows with a blank rate.
    ('paving', 'labor_curb_lf',             0.00,  'CURB, D66 — blank on this job'),
    ('paving', 'labor_rebar_lb',            0.00,  'REBAR, D65 — blank on this job')
ON CONFLICT (kind, key) DO NOTHING;

-- Sidewalks ride with paving until 11-Sidewalks is read, the same assumption
-- sql/035 recorded for their labor rates.
INSERT INTO assembly_rates (kind, key, value, note)
SELECT 'sidewalk', key, value, 'Assumed as paving until 11-Sidewalks is read'
FROM assembly_rates
WHERE kind = 'paving'
ON CONFLICT (kind, key) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- Four workbook bugs this build does NOT reproduce
--
-- On the paving sheet, five cells in the lumber block price as `=T*R` where
-- every neighbour prices as `=T*R*(1+tax)`. One of them is right — concrete
-- haul-off is a hauling service, and it stays untaxed here. The other four are
-- materials that are plainly taxable:
--
--     3/8" x 12" x 16' siding      $360.00
--     slab cure                  $8,512.50
--     3/4" smooth dowels         $8,637.40
--     form release                   $0.00  (zero qty on this job)
--                                ----------
--                               $17,509.90  x 8.25%  =  $1,444.57
--
-- So the app reads $1,328,628.04 against the sheet's $1,327,183.47: +0.109%,
-- every cent of it named. There is also a $67.75 difference on steel, because
-- the app weighs #3 bar at the ASTM 0.376 lb/ft that the whole rest of the
-- system uses and the sheet computes 0.3757154 from (size/16)^2 x 10.6870159.
--
-- Verify:
--   SELECT kind, key, value, note FROM assembly_rates WHERE kind = 'paving'
--   ORDER BY key;
