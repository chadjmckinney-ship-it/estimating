-- 074_slabs.sql
--
-- Slabs: the workbook's 05-Slabs tab as a kind of its own on the mono-slab
-- engine. Chad, 2026-09-07: "ok, lets do slabs".
--
-- 05-Slabs is the 04 mono-slab tab, cell for cell, used for a conventional
-- (rebar) slab on grade: the same pour row — SF, thickness, sand, perimeter,
-- a mat as a bar size at a spacing, a mix — the same lumber block, the same
-- vapor barrier, the same equipment ladder. What makes it its own kind is
-- what the tab types differently: rebar at grade-beam bar (G70 reads
-- Pricing!D23), tie steel at $350 with the first 0.35 lb/SF carried (U10 =
-- P10 - SF x 0.35), no support-steel allowance, sand without waste (K73 is
-- blank), the labor rates ($0.25 forming, $0.50 grading, $0.50 place and
-- finish, $0.20 wreck), joints SAWN at 20 ft both ways ($0.55/LF, D105 = y)
-- with a sealant switch left off, the pump at $10, haul-off at $12, the 2x10
-- run once around the perimeter where 04 runs it twice, form% 1, and a TYPED
-- superintendent (E91 is a cell here, SF / 16,000 x 7 on 04). The LBJ tab is
-- empty; the Pearl Landing Podium job carries it at 56,522 SF, $349,626.42
-- cost and $419,551.70 sale, and that is the golden (tests/slabs_fixture.py).
--
-- No new table: the pours are mono_slabs rows, and the kind already exists
-- in SECTION_KINDS and the kind check. This seeds the tab's rates and puts
-- the monetary ones on every existing job's price sheet.

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('slabs', 'labor_forming_sf',               0.25,  '05-Slabs E79'),
    ('slabs', 'labor_grading_sf',               0.5,   '05-Slabs E80'),
    ('slabs', 'labor_place_finish_sf',          0.5,   '05-Slabs E81'),
    ('slabs', 'labor_wreck_sf',                 0.2,   '05-Slabs E82'),
    ('slabs', 'labor_drops_ff',                 8,     '05-Slabs E83'),
    ('slabs', 'labor_excavation_cy',            12,    '05-Slabs E85'),
    ('slabs', 'labor_hold_down_ea',             85,    '05-Slabs E86 — 04 types 100'),
    ('slabs', 'labor_tie_steel_ton',            350,   '05-Slabs E87 — 04 types 450'),
    ('slabs', 'labor_tie_steel_free_lb_per_sf', 0.35,  '05-Slabs U10: the first 0.35 lb/SF is carried, not tied'),
    ('slabs', 'support_rebar_lb_per_sf',        0,     '05-Slabs P10 is the mat and its waste alone — no support steel'),
    ('slabs', 'waste_sand',                     0,     '05-Slabs K73 is blank'),
    ('slabs', 'waste_concrete',                 0.06,  '05-Slabs K65'),
    ('slabs', 'waste_rebar',                    0.10,  '05-Slabs K70'),
    ('slabs', 'form_percent',                   1,     '05-Slabs W65 — 04 types 0.7'),
    ('slabs', 'concrete_pump_cy',               10,    '05-Slabs G106'),
    ('slabs', 'haul_off_cy',                    12,    '05-Slabs G107'),
    ('slabs', 'engineering_sf',                 0.2,   '05-Slabs G103'),
    ('slabs', 'saw_cutting_lf',                 0.55,  '05-Slabs G105 — joints sawn both ways'),
    ('slabs', 'saw_joint_spacing_ft',           20,    '05-Slabs L105 — joint spacing, feet'),
    ('slabs', 'joint_control_lf',               0.65,  '05-Slabs G104 — the sealant on the sawn joints, a switch the tab leaves at n'),
    ('slabs', 'carton_forms_sf',                1.35,  '05-Slabs G75 — carton forms under the slab, a switch (F75)')
ON CONFLICT (kind, key) DO NOTHING;

-- The price sheets: the kind's monetary rates on every existing job, at the
-- assembly value, so nothing reads unpriced until the next pull.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', a.kind, a.key, k.label, k.unit, a.kind || ' rates', a.value, a.value
  FROM estimates e
 CROSS JOIN assembly_rates a
  JOIN (VALUES
          ('labor_forming_sf',      'Forming labor',          'SF'),
          ('labor_grading_sf',      'Grading labor',          'SF'),
          ('labor_place_finish_sf', 'Place & finish labor',   'SF'),
          ('labor_wreck_sf',        'Wreck & clean labor',    'SF'),
          ('labor_drops_ff',        'Drops labor',            'FF'),
          ('labor_excavation_cy',   'Excavation labor',       'CY'),
          ('labor_hold_down_ea',    'Hold-down labor',        'EA'),
          ('labor_tie_steel_ton',   'Tie steel labor',        'TON'),
          ('concrete_pump_cy',      'Concrete pump',          'CY'),
          ('haul_off_cy',           'Haul off',               'CY'),
          ('engineering_sf',        'Engineering',            'SF'),
          ('saw_cutting_lf',        'Saw cutting',            'LF'),
          ('joint_control_lf',      'Control joint',          'LF'),
          ('carton_forms_sf',       'Carton forms',           'SF')
       ) AS k(key, label, unit) ON k.key = a.key
 WHERE a.kind = 'slabs'
   AND EXISTS (SELECT 1 FROM estimate_prices p WHERE p.estimate_id = e.id)
ON CONFLICT DO NOTHING;
