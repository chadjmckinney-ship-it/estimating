-- 088_cost_codes.sql
--
-- The estimate Summary: the workbook's Summary tab, read off the app.
--
-- Chad, 2026-09-09: "there is something missing that the office uses from
-- the estimates.. a summary like that is in the excel spreadsheet.. pulls
-- all the materials form each section, supervision, everything thats in a
-- project.. a total of each the a breakdown per section.." — and, on the
-- proposal, "build it".
--
-- The tab is two tables. The JOB COST SUMMARY: a row per section with its
-- quantity, its sale and fifteen money columns (forms & accessories, grade
-- material, poly/sealing, PT cables, rebar, rebar accessories, concrete,
-- seal/waterproofing/cure, other subs, sub labor, labor, supervision, PM,
-- equipment, out of town), a $/unit line under each, the totals and each
-- column's share of the price, then TOTAL MATERIAL / LABOR / SUB LABOR /
-- OTHER, Margin Contingency and ESTIMATED PROFIT. And the COST CODES: the
-- chart from 000001 General Requirements to 000091 Margin Contingency, a
-- Summary column and a column per section, every dollar of a section's cost
-- filed under a code (each tab's E120:E177 says where its lines go).
--
-- cost_codes is that chart, as the LBJ workbook carries it, each code with
-- the job-cost column it feeds. cost_code_lines says where each line the app
-- prices is filed: a purchase the material-costs reader reports (concrete,
-- rebar, PT, sand, poly...), a forming-materials line, a labor line, an
-- equipment or contract line, a misc item's typed allowance, the fuel &
-- maintenance uplift — by its code. A labor line carries a second code for a
-- section whose labor is in house rather than subcontracted (the chart keeps
-- both sets; the tab's Y/N column decides). The office moves a line to
-- another code from Settings and the summary follows; a line with no code
-- is shown as unassigned and still counted, never dropped.

CREATE TABLE IF NOT EXISTS cost_codes (
    code            text PRIMARY KEY,
    name            text NOT NULL,
    category        text NOT NULL CHECK (category IN (
                        'material', 'supervision', 'in_house_labor', 'contract_services',
                        'sub_labor', 'equipment', 'travel', 'misc', 'other')),
    -- The JOB COST SUMMARY column this code's dollars land in; NULL for a
    -- code that is a subtotal of others (000040, 000060), is not used, or is
    -- the margin line, which the lower block carries on its own.
    summary_column  text CHECK (summary_column IN (
                        'forms_accessories', 'grade_material', 'poly_sealing', 'pt_cables', 'rebar',
                        'rebar_accessories', 'concrete', 'seal_cure', 'other_subs', 'sub_labor',
                        'labor', 'supervision', 'pm', 'equipment', 'out_of_town')),
    is_subtotal     boolean NOT NULL DEFAULT false,
    sort_order      integer NOT NULL DEFAULT 0
);
COMMENT ON TABLE cost_codes IS 'The workbook''s cost codes (sql/088): the rows of the Summary tab''s breakdown, each with the job-cost column it feeds.';

CREATE TABLE IF NOT EXISTS cost_code_lines (
    line_kind      text NOT NULL CHECK (line_kind IN ('purchase', 'material', 'labor', 'equipment', 'misc', 'uplift')),
    line_code      text NOT NULL,
    cost_code      text NOT NULL REFERENCES cost_codes (code),
    inhouse_code   text REFERENCES cost_codes (code),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    updated_by     uuid REFERENCES estimators (id) ON DELETE SET NULL,
    PRIMARY KEY (line_kind, line_code)
);
CREATE INDEX IF NOT EXISTS cost_code_lines_code_idx ON cost_code_lines (cost_code);
CREATE INDEX IF NOT EXISTS cost_code_lines_inhouse_idx ON cost_code_lines (inhouse_code);
CREATE INDEX IF NOT EXISTS cost_code_lines_updated_by_idx ON cost_code_lines (updated_by);
COMMENT ON TABLE cost_code_lines IS 'Where each priced line is filed (sql/088): a purchase key, a forming code, a labor code, an equipment code, a misc allowance or an uplift -> a cost code; inhouse_code for a section whose labor is not subcontracted.';

INSERT INTO cost_codes (code, name, category, summary_column, is_subtotal, sort_order) VALUES
    ('000001', 'General Requirements',      'material',          'forms_accessories', false,  1),
    ('000002', 'Lumber',                    'material',          'forms_accessories', false,  2),
    ('000003', 'Sand Material',             'material',          'grade_material',    false,  3),
    ('000004', 'Rock Material',             'material',          'grade_material',    false,  4),
    ('000005', 'Reinforcement Material',    'material',          'rebar',             false,  5),
    ('000006', 'Reinforcement Accessories', 'material',          'rebar_accessories', false,  6),
    ('000007', 'PT Cables',                 'material',          'pt_cables',         false,  7),
    ('000008', 'Concrete Material',         'material',          'concrete',          false,  8),
    ('000009', 'Carton Forms',              'material',          'forms_accessories', false,  9),
    ('000010', 'Cure/Sealers',              'material',          'seal_cure',         false, 10),
    ('000011', 'Patch/Grout',               'material',          'forms_accessories', false, 11),
    ('000012', 'Poly/Vapor Barrier',        'material',          'poly_sealing',      false, 12),
    ('000013', 'Special Material',          'material',          'forms_accessories', false, 13),
    ('000014', 'Special Material 2',        'material',          'forms_accessories', false, 14),
    ('000015', 'PPE/Safety',                'material',          'forms_accessories', false, 15),
    ('000020', 'Supervision',               'supervision',       'supervision',       false, 20),
    ('000021', 'Supervision Expense',       'supervision',       'supervision',       false, 21),
    ('000022', 'Project Management',        'supervision',       'pm',                false, 22),
    ('000023', 'Labor Grade, Poly, Reinf.', 'in_house_labor',    'labor',             false, 23),
    ('000024', 'Labor Place & Finish',      'in_house_labor',    'labor',             false, 24),
    ('000025', 'Labor Drops',               'in_house_labor',    'labor',             false, 25),
    ('000026', 'Labor Strip Forms',         'in_house_labor',    'labor',             false, 26),
    ('000027', 'Labor Burden',              'in_house_labor',    'labor',             false, 27),
    ('000028', 'Surveying',                 'in_house_labor',    'other_subs',        false, 28),
    ('000030', 'Pumping',                   'contract_services', 'other_subs',        false, 30),
    ('000031', 'Earth Work/Excavation',     'contract_services', 'other_subs',        false, 31),
    ('000032', 'Drilling',                  'contract_services', 'other_subs',        false, 32),
    ('000033', 'Haul off',                  'contract_services', 'other_subs',        false, 33),
    ('000034', 'Saw Cutting/Sealing',       'contract_services', 'other_subs',        false, 34),
    ('000035', 'Demolition',                'contract_services', 'other_subs',        false, 35),
    ('000037', 'Waterproofing',             'contract_services', 'seal_cure',         false, 37),
    ('000038', 'Crane/Hoisting',            'contract_services', 'other_subs',        false, 38),
    ('000039', 'Forming Systems',           'contract_services', 'other_subs',        false, 39),
    ('000040', 'Total Sub Labor',           'sub_labor',         NULL,                true,  40),
    ('000041', 'Labor Forming',             'sub_labor',         'sub_labor',         false, 41),
    ('000042', 'Labor Grade, Poly, Reinf.', 'sub_labor',         'sub_labor',         false, 42),
    ('000043', 'Labor Place & Finish',      'sub_labor',         'sub_labor',         false, 43),
    ('000044', 'Labor Drops',               'sub_labor',         'sub_labor',         false, 44),
    ('000045', 'Labor Strip Forms',         'sub_labor',         'sub_labor',         false, 45),
    ('000046', 'Labor Burden',              'sub_labor',         'sub_labor',         false, 46),
    ('000047', 'Rebar',                     'sub_labor',         'sub_labor',         false, 47),
    ('000048', 'PT Installation',           'sub_labor',         'sub_labor',         false, 48),
    ('000049', 'Extra Hours',               'sub_labor',         'sub_labor',         false, 49),
    ('000060', 'Total Equipment Rental',    'equipment',         NULL,                true,  60),
    ('000061', 'SkyTrack',                  'equipment',         'equipment',         false, 61),
    ('000062', 'Mini Excavator',            'equipment',         'equipment',         false, 62),
    ('000063', 'Trencher',                  'equipment',         'equipment',         false, 63),
    ('000064', 'Skid Steer',                'equipment',         'equipment',         false, 64),
    ('000065', 'General Equipment Rental',  'equipment',         'equipment',         false, 65),
    ('000066', 'Fuel',                      'equipment',         'equipment',         false, 66),
    ('000067', 'Purchased Tools',           'equipment',         'equipment',         false, 67),
    ('000068', 'Stolen/Damaged',            'equipment',         'equipment',         false, 68),
    ('000070', 'Out of Town Expense',       'travel',            'out_of_town',       false, 70),
    ('000071', 'Miscellaneous',             'misc',              'other_subs',        false, 71),
    ('000072', 'Repairs',                   'misc',              'other_subs',        false, 72),
    ('000073', 'Engineering',               'misc',              'other_subs',        false, 73),
    ('000090', 'Not Used',                  'other',             NULL,                false, 90),
    ('000091', 'Margin Contingency',        'other',             NULL,                false, 91)
ON CONFLICT (code) DO NOTHING;

-- Where each line goes. The workbook's own filing where the tab has one
-- (the PT slab tab's E120:E177), the nearest code where it does not.
INSERT INTO cost_code_lines (line_kind, line_code, cost_code, inhouse_code) VALUES
    -- the purchases the material-costs reader reports (services/material_costs.py);
    -- 'rounding' is that reader's per-row cents, filed with the concrete
    ('purchase', 'concrete',         '000008', NULL),
    ('purchase', 'wall_concrete',    '000008', NULL),
    ('purchase', 'footing_concrete', '000008', NULL),
    ('purchase', 'rounding',         '000008', NULL),
    ('purchase', 'rebar',            '000005', NULL),
    ('purchase', 'mesh',             '000005', NULL),
    ('purchase', 'pt',               '000007', NULL),
    ('purchase', 'sand',             '000003', NULL),
    ('purchase', 'poly',             '000012', NULL),
    ('purchase', 'tape',             '000012', NULL),
    ('purchase', 'weld_plates',      '000006', NULL),
    ('purchase', 'drilling',         '000032', NULL),
    -- the forming-materials block (services/forming.py), by line code:
    -- the tab files the whole lumber block under Lumber
    ('material', '2x4',              '000002', NULL), ('material', '2x4_brace',     '000002', NULL),
    ('material', '2x6',              '000002', NULL), ('material', '2x8',           '000002', NULL),
    ('material', '2x10',             '000002', NULL), ('material', 'ply',           '000002', NULL),
    ('material', 'plywood_forming',  '000002', NULL), ('material', 'ledge_2x6',     '000002', NULL),
    ('material', 'ledge_ply',        '000002', NULL), ('material', 'stakes',        '000002', NULL),
    ('material', '6p',               '000002', NULL), ('material', '8p',            '000002', NULL),
    ('material', '16p',              '000002', NULL), ('material', '20p',           '000002', NULL),
    ('material', 'form_release',     '000002', NULL), ('material', 'camlocks',      '000002', NULL),
    ('material', 'wall_ties',        '000002', NULL), ('material', 'chamfer',       '000002', NULL),
    ('material', 'keyway',           '000002', NULL), ('material', 'bracing',       '000002', NULL),
    ('material', 'pipe_brace',       '000002', NULL), ('material', 'turnbuckles',   '000002', NULL),
    ('material', 'rw4',              '000002', NULL), ('material', 'rw6',           '000002', NULL),
    ('material', 'rw8',              '000002', NULL), ('material', 'reveal',        '000002', NULL),
    ('material', 'siding',           '000002', NULL), ('material', 'tack_strip',    '000002', NULL),
    ('material', 'tack_strips',      '000002', NULL), ('material', 'texture_comb',  '000002', NULL),
    ('material', 'water_stop',       '000002', NULL), ('material', 'anchors',       '000002', NULL),
    ('material', 'durrock_retainer', '000002', NULL), ('material', 'ada_bricks',    '000002', NULL),
    ('material', 'pier_boots',       '000002', NULL), ('material', 'pier_sleds',    '000002', NULL),
    ('material', 'pavecrete',        '000002', NULL),
    ('material', 'rock',             '000004', NULL),
    ('material', 'mesh',             '000005', NULL), ('material', 'stud_rails',    '000005', NULL),
    ('material', 'accessories',      '000006', NULL), ('material', 'chairs',        '000006', NULL),
    ('material', 'bolsters',         '000006', NULL), ('material', 'tie_wire',      '000006', NULL),
    ('material', 'dowels',           '000006', NULL), ('material', 'dowel_baskets', '000006', NULL),
    ('material', 'smooth_dowels',    '000006', NULL),
    ('material', 'carton_forms',     '000009', NULL),
    ('material', 'cure',             '000010', NULL),
    ('material', 'patch',            '000011', NULL),
    ('material', 'bond_breaker',     '000013', NULL), ('material', 'french_drain',  '000013', NULL),
    ('material', 'lift_inserts',     '000013', NULL), ('material', 'brace_inserts', '000013', NULL),
    ('material', 'haul_off',         '000033', NULL),
    ('material', 'form_rental',      '000039', NULL), ('material', 'shoring_rental', '000039', NULL),
    ('material', 'reshoring',        '000039', NULL),
    -- labor lines (services/labor.py): the sub-labor code, and the in-house
    -- code where the chart has one (the tab: grading -> 000023, place &
    -- finish -> 000024, drops -> 000025, wreck -> 000026, tie steel -> 000023)
    ('labor', 'superintendent',  '000020', NULL), ('labor', 'foreman',       '000020', NULL),
    ('labor', 'expense',         '000021', NULL), ('labor', 'pm',            '000022', NULL),
    ('labor', 'forming',         '000041', NULL), ('labor', 'gb_forming',    '000041', NULL),
    ('labor', 'footings',        '000041', NULL), ('labor', 'curb',          '000041', NULL),
    ('labor', 'thick_edge',      '000041', NULL), ('labor', 'edge_rails',    '000041', NULL),
    ('labor', 'pilasters',       '000041', NULL), ('labor', 'pier_caps',     '000041', NULL),
    ('labor', 'brick_ledge',     '000041', NULL), ('labor', 'build_up',      '000041', NULL),
    ('labor', 'hold_downs',      '000041', NULL), ('labor', 'stair_treads',  '000041', NULL),
    ('labor', 'ada_ramps',       '000041', NULL), ('labor', 'french_drains', '000041', NULL),
    ('labor', 'reshoring',       '000041', NULL),
    ('labor', 'grading',         '000042', '000023'), ('labor', 'layout',     '000042', '000023'),
    ('labor', 'backfill',        '000042', '000023'), ('labor', 'excavate',   '000042', '000023'),
    ('labor', 'excavation',      '000042', '000023'),
    ('labor', 'place_finish',    '000043', '000024'), ('labor', 'rub_patch',  '000043', '000024'),
    ('labor', 'drops',           '000044', '000025'),
    ('labor', 'wreck',           '000045', '000026'), ('labor', 'cleanup',    '000045', '000026'),
    ('labor', 'labor_add',       '000046', '000027'),
    ('labor', 'tie_steel',       '000047', '000023'), ('labor', 'rebar',      '000047', '000023'),
    ('labor', 'stud_rails',      '000047', '000023'),
    ('labor', 'cable_placement', '000048', '000023'),
    ('labor', 'extra_hours',     '000049', NULL),
    -- equipment lines (services/estimate_equipment.py): the rentals, then the contract services
    ('equipment', 'skytrack',       '000061', NULL), ('equipment', 'mini_excavator', '000062', NULL),
    ('equipment', 'trencher',       '000063', NULL), ('equipment', 'skid_steer',     '000064', NULL),
    ('equipment', 'bobcat',         '000064', NULL), ('equipment', 'backhoe',        '000065', NULL),
    ('equipment', 'compactor',      '000065', NULL), ('equipment', 'fork_truck',     '000065', NULL),
    ('equipment', 'light_tower',    '000065', NULL), ('equipment', 'sky_lift',       '000065', NULL),
    ('equipment', 'lift_20_ton',    '000065', NULL), ('equipment', 'misc_equip',     '000065', NULL),
    ('equipment', 'storage',        '000065', NULL), ('equipment', 'vault',          '000065', NULL),
    ('equipment', 'barricades',     '000065', NULL), ('equipment', 'easy_drill',     '000032', NULL),
    ('equipment', 'crane',          '000038', NULL), ('equipment', 'hoisting',       '000038', NULL),
    ('equipment', 'form_rental',    '000039', NULL), ('equipment', 'slip_forming',   '000039', NULL),
    ('equipment', 'concrete_pump',  '000030', NULL), ('equipment', 'haul_off',       '000033', NULL),
    ('equipment', 'saw_cutting',    '000034', NULL), ('equipment', 'saw_joint_sealant', '000034', NULL),
    ('equipment', 'soft_cut',       '000034', NULL), ('equipment', 'joint_construction', '000034', NULL),
    ('equipment', 'joint_control',  '000034', NULL), ('equipment', 'demo',           '000035', NULL),
    ('equipment', 'waterproofing',  '000037', NULL), ('equipment', 'surveying',      '000028', NULL),
    ('equipment', 'engineering',    '000073', NULL), ('equipment', 'panel_engineering', '000073', NULL),
    ('equipment', 'out_of_town',    '000070', NULL), ('equipment', 'mobilization',   '000071', NULL),
    ('equipment', 'misc_contract',  '000071', NULL), ('equipment', 'freight',        '000071', NULL),
    ('equipment', 'acid_etch',      '000071', NULL), ('equipment', 'stamping',       '000071', NULL),
    ('equipment', 'cure',           '000010', NULL), ('equipment', 'integral_color', '000013', NULL),
    -- a miscellaneous item's typed allowances (sql/078): the tab files its
    -- forms under Lumber, its supervision under Supervision, its equipment
    -- under Skid Steer, and spreads its labor over the eight sub-labor codes;
    -- here the labor is one line, filed as forming, or place & finish in house
    ('misc', 'forms',       '000002', NULL),
    ('misc', 'labor',       '000041', '000024'),
    ('misc', 'supervision', '000020', NULL),
    ('misc', 'equipment',   '000064', NULL),
    -- fuel & maintenance on the rental days (equip_fuel_maint_pct): the tab
    -- books the rentals' uplift to Fuel
    ('uplift', 'fuel',      '000066', NULL)
ON CONFLICT (line_kind, line_code) DO NOTHING;
