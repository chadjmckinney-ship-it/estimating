-- 049 — the estimate price sheet, stage 2: equipment and every monetary rate
--
-- docs/specs/estimate-price-sheet-spec.md. Stage 1 (048) put mixes and materials
-- on the sheet. This puts on it everything else that is a PRICE and lives in
-- a table:
--
--   equipment.unit_cost                 the rental day rates
--   system_settings  (monetary keys)    superintendent/day, forming $/SF, sales tax…
--   assembly_rates   (monetary keys)    the same keys where an assembly overrides
--
-- and NOT the rules that share those tables — waste factors, SF-per-box
-- divisors, supervision pacing, pier geometry. The split is enumerated by
-- hand below and in services/price_book.MONETARY_KEYS; a test holds the two
-- lists equal, and another fails when a key appears in either table that is
-- on neither list. There is no naming convention to lean on: `labor_forming_sf`
-- is dollars per SF and `nails_16p_per_sf` is SF per box.
--
-- The spec's stages 2 and 3 land together because they are one mechanism:
-- `_rate_numeric` reads assembly_rates then system_settings, and the sheet
-- keeps both levels (scope = assembly kind, or NULL for the company row) so
-- a sheeted estimate resolves exactly as before, frozen at its pull.
--
-- The backfill moves no number: every existing estimate gets the tables'
-- current values, which is what it was pricing from a moment ago.

-- The monetary keys, once, so the three backfills below share one list.
DROP TABLE IF EXISTS monetary_keys;
CREATE TEMP TABLE monetary_keys (key text PRIMARY KEY, label text NOT NULL, unit text NOT NULL);
INSERT INTO monetary_keys (key, label, unit) VALUES
    ('labor_super_day_rate', 'Superintendent', 'DAY'),
    ('labor_foreman_day_rate', 'Foreman', 'DAY'),
    ('labor_pm_day_rate', 'Project manager', 'DAY'),
    ('labor_expense_day_rate', 'Field expense', 'DAY'),
    ('labor_forming_sf', 'Forming labor', 'SF'),
    ('labor_place_finish_sf', 'Place & finish labor', 'SF'),
    ('labor_place_finish_ea', 'Place & finish labor', 'EA'),
    ('labor_wreck_sf', 'Wreck forms labor', 'SF'),
    ('labor_grading_sf', 'Grading labor', 'SF'),
    ('labor_tie_steel_ton', 'Tie steel labor', 'TON'),
    ('labor_rebar_lb', 'Rebar labor', 'LB'),
    ('labor_excavation_cy', 'Excavation labor', 'CY'),
    ('labor_excavate_cy', 'Excavate labor', 'CY'),
    ('labor_backfill_cy', 'Backfill labor', 'CY'),
    ('labor_drops_ff', 'Drops labor', 'FF'),
    ('labor_hold_down_ea', 'Hold-downs labor', 'EA'),
    ('labor_brick_ledge_lf', 'Brick ledge labor', 'LF'),
    ('labor_curb_lf', 'Curb labor', 'LF'),
    ('labor_footings_sf', 'Footings labor', 'SF'),
    ('labor_french_drain_lf', 'French drain labor', 'LF'),
    ('labor_build_up_sf', 'Build-up labor', 'SF'),
    ('labor_rub_patch_sf', 'Rub & patch labor', 'SF'),
    ('labor_layout_ea', 'Layout labor', 'EA'),
    ('labor_cleanup_ea', 'Cleanup labor', 'EA'),
    ('labor_pier_cap_ea', 'Pier cap labor', 'EA'),
    ('labor_reshoring_sf', 'Reshoring labor', 'SF'),
    ('labor_edge_rails_lf', 'Edge & safety rails labor', 'LF'),
    ('labor_gb_forming_ff', 'Grade beam forming labor', 'FF'),
    ('labor_stud_rails_ton', 'Stud rails labor', 'TON'),
    ('labor_cable_placement_lb', 'PT cable placement labor', 'LB'),
    ('equip_misc_day_rate', 'Misc equipment', 'DAY'),
    ('equip_vault_day_rate', 'Vault', 'DAY'),
    ('equip_storage_day_rate', 'Storage', 'DAY'),
    ('equip_fork_truck_day_rate', 'Fork truck', 'DAY'),
    ('equip_easy_drill_day_rate', 'Easy drill', 'DAY'),
    ('equip_bobcat_day_rate', 'Bobcat', 'DAY'),
    ('equip_light_tower_day_rate', 'Light tower', 'DAY'),
    ('equip_skytrack_day_rate', 'SkyTrack', 'DAY'),
    ('equip_mini_excavator_day_rate', 'Mini excavator', 'DAY'),
    ('equip_hoisting_day_rate', 'Hoisting', 'DAY'),
    ('equip_skid_steer_day_rate', 'Skid steer', 'DAY'),
    ('equip_skid_day_rate', 'Skid steer', 'DAY'),
    ('equip_trencher_day_rate', 'Trencher', 'DAY'),
    ('equip_crane_day_rate', 'Crane & operator', 'DAY'),
    ('equip_20_ton_lift_day_rate', '20 ton lift', 'DAY'),
    ('out_of_town_day_rate', 'Out of town', 'DAY'),
    ('mobilization_ls', 'Mobilization', 'LS'),
    ('concrete_pump_cy', 'Concrete pump', 'CY'),
    ('haul_off_cy', 'Haul off', 'CY'),
    ('cure_sf', 'Cure', 'SF'),
    ('saw_cutting_lf', 'Saw cutting', 'LF'),
    ('joint_construction_lf', 'Construction joint', 'LF'),
    ('joint_control_lf', 'Control joint', 'LF'),
    ('joint_soft_cut_lf', 'Soft-cut joint', 'LF'),
    ('demo_lf', 'Demo', 'LF'),
    ('stamping_sf', 'Stamping', 'SF'),
    ('slip_form_sf', 'Slip form', 'SF'),
    ('surveying_ea', 'Surveying', 'EA'),
    ('waterproofing_sf', 'Waterproofing', 'SF'),
    ('barricades_month', 'Barricades', 'MONTH'),
    ('barricades_lf', 'Barricades', 'LF'),
    ('engineering_sf', 'Engineering', 'SF'),
    ('freight_load', 'Freight', 'LOAD'),
    ('pt_cable_sf', 'PT cable', 'SF'),
    ('stud_rails_lb', 'Stud rails', 'LB'),
    ('carton_forms_sf', 'Carton forms', 'SF'),
    ('plywood_forming_sf', 'Plywood forming', 'SF'),
    ('form_rental_shoring_sf', 'Form rental shoring', 'SF'),
    ('reshoring_material_sf', 'Reshoring material', 'SF'),
    ('form_rental_contact_ft', 'Form rental', 'CONTACT FT'),
    ('rock_cy', 'Rock', 'CY'),
    ('sand_unit_cost', 'Sand', 'CY'),
    ('sales_tax_pct', 'Sales tax', 'RATIO'),
    ('equip_fuel_maint_pct', 'Fuel & maintenance on rentals', 'RATIO');

-- Equipment: catalog day rates. A $0 row is unpriced (_equip_price has never
-- taken a zero as a price) and is skipped, like a NULL mix in 048.
INSERT INTO estimate_prices
    (estimate_id, kind, ref_id, label, unit, category, catalog_value, value)
SELECT e.id, 'equipment', q.id, q.name, coalesce(q.unit, 'DAY'), 'equipment',
       q.unit_cost, q.unit_cost
  FROM estimates e
 CROSS JOIN equipment q
 WHERE q.is_active AND q.unit_cost IS NOT NULL AND q.unit_cost > 0
ON CONFLICT DO NOTHING;

-- Company settings that are prices.
INSERT INTO estimate_prices
    (estimate_id, kind, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'setting', s.key, k.label, k.unit, 'labor & company rates',
       (s.value #>> '{}')::numeric, (s.value #>> '{}')::numeric
  FROM estimates e
 CROSS JOIN system_settings s
  JOIN monetary_keys k ON k.key = s.key
 WHERE (s.value #>> '{}') ~ '^-?[0-9]+(\.[0-9]+)?$'
ON CONFLICT DO NOTHING;

-- Assembly overrides of those prices. A zero here is a statement (paving
-- pumps nothing) and is copied as such.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', a.kind, a.key, k.label, k.unit, a.kind || ' rates',
       a.value, a.value
  FROM estimates e
 CROSS JOIN assembly_rates a
  JOIN monetary_keys k ON k.key = a.key
ON CONFLICT DO NOTHING;

DROP TABLE monetary_keys;
