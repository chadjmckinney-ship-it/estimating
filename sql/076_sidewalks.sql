-- 076_sidewalks.sql
--
-- Sidewalks: the older template's SIDEWALKS tab as the `sidewalk` kind's own
-- line sets, on the paving-family engine. Chad, 2026-09-08, on being asked
-- whether sidewalks were done: "do you want me to populate the sidewalk tab
-- so you have numbers to go off of?" — and populated
-- workbooks/Downloads/Updated_Estimate_Worksheet_from_Estimate_Project.xlsm,
-- SIDEWALKS: three types, 40,075 SF, $394,411.82 cost, $485,126.54 sale.
-- That tab is the golden (tests/sidewalks_fixture.py).
--
-- Until now the kind rode the paving engine on rates sql/035 marked
-- "Assumed as paving until 11-Sidewalks is read". The tab is not the paving
-- tab: one row per walk type carries SF, thickness, sand, mix, a thickened
-- edge, three finishes (stamped, integral color, acid etch or sandblast),
-- traffic control, stair treads as LF x rise x run, a bar mat and a mesh
-- gauge. Its lumber runs off SQUARE FEET, not curb; its supervision derives
-- from CONCRETE (D57 = CY / 10 x 1.5 + 5); its labor is $1.75 forming, $1.00
-- place and finish, $0.25 wreck per SF, with the thick edge at $10/LF, stair
-- treads at $2/LF and ADA ramps at $400 each; the finishes are contract
-- lines at $3.50/SF stamped, $100/CY of colored concrete, $2/SF acid etch.

-- The area row: three finishes and the stair treads (the thick edge and the
-- traffic flag were already there for paving, sql/036).
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS stamped              boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS integral_color       boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS acid_etch            boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS stair_tread_lf       numeric(14, 3),
    ADD COLUMN IF NOT EXISTS stair_tread_rise_in  numeric(8, 3),
    ADD COLUMN IF NOT EXISTS stair_tread_run_in   numeric(8, 3),
    ADD COLUMN IF NOT EXISTS calc_stair_concrete_cy numeric(14, 4),
    ADD COLUMN IF NOT EXISTS calc_edge_rebar_lb     numeric(14, 3);
COMMENT ON COLUMN mono_slabs.stair_tread_lf IS
    'Sidewalks (sql/076): stair treads, LF; concrete = LF x rise x (run + 12) / 3888, labor per LF.';
COMMENT ON COLUMN mono_slabs.calc_edge_rebar_lb IS
    'Sidewalks (sql/076): the bars along the thickened edge, LF x count x lb/ft, outside the mat''s waste.';

-- The rates. sql/035's five guesses go; the tab's own numbers come in.
DELETE FROM assembly_rates WHERE kind = 'sidewalk';
DELETE FROM estimate_prices WHERE scope = 'sidewalk' AND kind = 'assembly_rate';
DELETE FROM section_rates WHERE key IN ('labor_super_sf_per_week', 'labor_grading_sf')
   AND section_id IN (SELECT id FROM estimate_sections WHERE kind = 'sidewalk');

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('sidewalk', 'labor_forming_sf',            1.75,  'SIDEWALKS D49'),
    ('sidewalk', 'labor_place_finish_sf',       1,     'SIDEWALKS D50'),
    ('sidewalk', 'labor_wreck_sf',              0.25,  'SIDEWALKS D51'),
    ('sidewalk', 'labor_thick_edge_lf',         10,    'SIDEWALKS D53'),
    ('sidewalk', 'labor_stair_tread_lf',        2,     'SIDEWALKS D54'),
    ('sidewalk', 'labor_ada_ramp_ea',           400,   'SIDEWALKS D52 — a typed count'),
    ('sidewalk', 'labor_super_days_per_cy',     0.15,  'SIDEWALKS D57: CY / 10 x 1.5 ...'),
    ('sidewalk', 'labor_super_days_fixed',      5,     'SIDEWALKS D57: ... + 5 days'),
    ('sidewalk', 'waste_concrete',              0.08,  'SIDEWALKS M38'),
    ('sidewalk', 'waste_rebar',                 0.10,  'SIDEWALKS M41'),
    ('sidewalk', 'waste_sand',                  0.05,  'SIDEWALKS M44'),
    ('sidewalk', 'support_rebar_lb_per_sf',     0,     'SIDEWALKS U10 is the mat, its waste and the edge bars alone'),
    ('sidewalk', 'vapor_barrier_enabled',       0,     'no poly line on the SIDEWALKS tab'),
    ('sidewalk', 'thick_edge_width_ft',         1.8,   'SIDEWALKS V10: H x 1.8 x 0.18 / 27 — paving digs 1.5'),
    ('sidewalk', 'thick_edge_bars',             2,     'SIDEWALKS U10: two bars along the edge'),
    ('sidewalk', 'thick_edge_bar_size',         3,     'SIDEWALKS Y34: #3'),
    ('sidewalk', 'joint_construction_spacing_ft', 15,  'SIDEWALKS N68 — expansion joints'),
    ('sidewalk', 'joint_control_spacing_ft',    5,     'SIDEWALKS N69 — control joints, two passes less the expansion'),
    ('sidewalk', 'joint_construction_lf',       0,     'SIDEWALKS D68 — expansion joint sealant, typed 0'),
    ('sidewalk', 'joint_control_lf',            0,     'SIDEWALKS D69 — control joint sealant, typed 0'),
    ('sidewalk', 'saw_cutting_lf',              0,     'SIDEWALKS D70 — typed 0'),
    ('sidewalk', 'haul_off_cy',                 4,     'SIDEWALKS D71'),
    ('sidewalk', 'demo_lf',                     8,     'SIDEWALKS D72 — curb demo'),
    ('sidewalk', 'stamping_sf',                 3.5,   'SIDEWALKS D73 — stamped concrete, from the area''s flag'),
    ('sidewalk', 'integral_color_cy',           100,   'SIDEWALKS D74 — per CY of the colored areas'),
    ('sidewalk', 'acid_etch_sf',                2,     'SIDEWALKS D75 — sandblast / acid etch, from the flag'),
    ('sidewalk', 'misc_contract_ls',            1000,  'SIDEWALKS F77'),
    ('sidewalk', 'barricades_month',            1200,  'SIDEWALKS F66'),
    ('sidewalk', 'concrete_pump_cy',            0,     'no pump line on the SIDEWALKS tab — placed off the truck'),
    ('sidewalk', 'lumber_2x4_per_sf',           0.25,  'SIDEWALKS U38: SF / 4'),
    ('sidewalk', 'stakes_sf_per_bundle',        400,   'SIDEWALKS U44: SF / 8 / 50'),
    ('sidewalk', 'nails_16p_per_sf',            6000,  'SIDEWALKS U45'),
    ('sidewalk', 'nails_8p_per_sf',             6000,  'SIDEWALKS U46, with the 1.25'),
    ('sidewalk', 'tie_wire_sf_per_roll',        15000, 'SIDEWALKS U66'),
    ('sidewalk', 'cure_sf_per_drum',            16000, 'SIDEWALKS U72'),
    ('sidewalk', 'dowel_spacing_in',            18,    'SIDEWALKS U77')
ON CONFLICT (kind, key) DO NOTHING;

-- The price sheets: the kind's monetary rates on every existing job, at the
-- tab's values.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', a.kind, a.key, k.label, k.unit, a.kind || ' rates', a.value, a.value
  FROM estimates e
 CROSS JOIN assembly_rates a
  JOIN (VALUES
          ('labor_forming_sf',        'Forming labor',            'SF'),
          ('labor_place_finish_sf',   'Place & finish labor',     'SF'),
          ('labor_wreck_sf',          'Wreck & clean labor',      'SF'),
          ('labor_thick_edge_lf',     'Thick edge labor',         'LF'),
          ('labor_stair_tread_lf',    'Stair tread labor',        'LF'),
          ('labor_ada_ramp_ea',       'ADA ramp labor',           'EA'),
          ('joint_construction_lf',   'Construction joint',       'LF'),
          ('joint_control_lf',        'Control joint',            'LF'),
          ('saw_cutting_lf',          'Saw cutting',              'LF'),
          ('haul_off_cy',             'Haul off',                 'CY'),
          ('demo_lf',                 'Demo',                     'LF'),
          ('stamping_sf',             'Stamping',                 'SF'),
          ('integral_color_cy',       'Integral color',           'CY'),
          ('acid_etch_sf',            'Acid etch / sandblast',    'SF'),
          ('misc_contract_ls',        'Miscellaneous contract',   'LS'),
          ('barricades_month',        'Barricades',               'MONTH'),
          ('concrete_pump_cy',        'Concrete pump',            'CY')
       ) AS k(key, label, unit) ON k.key = a.key
 WHERE a.kind = 'sidewalk'
   AND EXISTS (SELECT 1 FROM estimate_prices p WHERE p.estimate_id = e.id)
ON CONFLICT DO NOTHING;
