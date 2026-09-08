-- 075_slab_on_deck.sql
--
-- Slab on deck: the workbook's 09-SLAB ON DECK tab as a kind of its own on
-- the mono-slab engine, beside the rebar slab (sql/074). Chad, 2026-09-08:
-- "ok, lets do slab on deck".
--
-- Every 09 tab in every workbook in the folder is the empty template — no
-- job has priced one — so this is built from the template's own cells, and
-- tests/slab_on_deck_fixture.py exercises those formulas on a takeoff of its
-- own rather than reconciling to a bid.
--
-- The tab is the 05-Slabs variant of the mono tab (a rebar slab: the mat, no
-- support steel, tie steel with a free allowance, a typed superintendent, a
-- live concrete haul-off) with what a slab on metal deck changes typed in:
-- forming at $0.05/SF (edge forms only), SLAB PREP at $0.10 where a slab on
-- grade grades, tie steel with the first 0.45 lb/SF carried (U10), the bar
-- at the PT-slab item (G70 reads Pricing!D22), the pump at $20 (it is
-- upstairs), form% 0.5, saw cutting at $0.35 with no joint formula (a typed
-- LF), a DEMO line at $1.75/LF where 04 and 05 carry ENGINEERING, the
-- trencher on the ladder with the excavator, skid steer and sky track blank,
-- and haul-off at $500 a load where the ground tabs type $250.

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('slab_on_deck', 'labor_forming_sf',               0.05,  '09-SLAB ON DECK E79 — edge forms only'),
    ('slab_on_deck', 'labor_grading_sf',               0.1,   '09-SLAB ON DECK E80 — the line is SLAB PREP here'),
    ('slab_on_deck', 'labor_place_finish_sf',          0.5,   '09-SLAB ON DECK E81'),
    ('slab_on_deck', 'labor_wreck_sf',                 0.2,   '09-SLAB ON DECK E82'),
    ('slab_on_deck', 'labor_drops_ff',                 8,     '09-SLAB ON DECK E83'),
    ('slab_on_deck', 'labor_excavation_cy',            12,    '09-SLAB ON DECK E85'),
    ('slab_on_deck', 'labor_hold_down_ea',             85,    '09-SLAB ON DECK E86'),
    ('slab_on_deck', 'labor_tie_steel_ton',            350,   '09-SLAB ON DECK E87'),
    ('slab_on_deck', 'labor_tie_steel_free_lb_per_sf', 0.45,  '09-SLAB ON DECK U10: the first 0.45 lb/SF is carried, not tied'),
    ('slab_on_deck', 'support_rebar_lb_per_sf',        0,     '09-SLAB ON DECK P10 is the mat and its waste alone'),
    ('slab_on_deck', 'waste_sand',                     0,     '09-SLAB ON DECK K73 is blank (and there is no sand on a deck)'),
    ('slab_on_deck', 'waste_concrete',                 0.06,  '09-SLAB ON DECK K65'),
    ('slab_on_deck', 'waste_rebar',                    0.10,  '09-SLAB ON DECK K70'),
    ('slab_on_deck', 'form_percent',                   0.5,   '09-SLAB ON DECK W65'),
    ('slab_on_deck', 'concrete_pump_cy',               20,    '09-SLAB ON DECK G106 — the slab is upstairs'),
    ('slab_on_deck', 'haul_off_cy',                    12,    '09-SLAB ON DECK G107'),
    ('slab_on_deck', 'demo_lf',                        1.75,  '09-SLAB ON DECK G103 — where 04 and 05 carry ENGINEERING'),
    ('slab_on_deck', 'saw_cutting_lf',                 0.35,  '09-SLAB ON DECK G105 — a typed LF, the tab has no joint formula'),
    ('slab_on_deck', 'saw_joint_spacing_ft',           20,    '09-SLAB ON DECK L105'),
    ('slab_on_deck', 'joint_control_lf',               0.65,  '09-SLAB ON DECK G104 — the sealant, a typed LF'),
    ('slab_on_deck', 'carton_forms_sf',                1.35,  '09-SLAB ON DECK G75 — a switch (F75), n')
ON CONFLICT (kind, key) DO NOTHING;

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
          ('demo_lf',               'Demo',                   'LF'),
          ('saw_cutting_lf',        'Saw cutting',            'LF'),
          ('joint_control_lf',      'Control joint',          'LF'),
          ('carton_forms_sf',       'Carton forms',           'SF')
       ) AS k(key, label, unit) ON k.key = a.key
 WHERE a.kind = 'slab_on_deck'
   AND EXISTS (SELECT 1 FROM estimate_prices p WHERE p.estimate_id = e.id)
ON CONFLICT DO NOTHING;
