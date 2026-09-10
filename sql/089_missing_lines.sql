-- 089_missing_lines.sql
--
-- The lines the Lakeside tie-out found missing (2026-09-10). Chad: "add the
-- missing line sets, light tower, compactor, place and finish".
--
-- Three additions, every line off by default, so no priced job moves until
-- somebody switches one on (the older LBJ tabs carry none of them; the
-- newer Lakeside tabs carry all of them):
--
--   * a LIGHT TOWER on the slab sets (mono slab, rebar slab, slab on deck),
--     priced off the catalog's TOWER LIGHT row like the one the beam, wall
--     and pier sets already carry;
--   * a COMPACTOR on the beam and wall/footing sets, priced off the
--     catalog's COMPACTOR row;
--   * FORMING, PLACE AND FINISH, WRECK AND CLEAN UP and RUB AND PATCH per
--     FACE FOOT on a spot footing -- the 06-Footings tab's rows 67-70, which
--     sql/072 left off the kind because that tab's face feet are the wall's
--     (zero on a footing). The newer Footings tab prices them: its FACE FT
--     column (AY) is length x thickness x count, the wall rule with the
--     footing's thickness for its height, and its contact feet (AX) are
--     twice that.
--
-- This migration is the rates for the footing lines: the walls tab's four,
-- copied the way sql/072 copied the rest of the kind (06-Footings is the
-- walls tab), and the same rows onto every existing estimate's price sheet.
-- The machines need nothing: their prices are the catalog's.

INSERT INTO assembly_rates (kind, key, value, note)
SELECT 'spot_footings', key, value,
       'copied from walls_footings (sql/089): the footings tab''s face-foot rows, per length x thickness'
  FROM assembly_rates
 WHERE kind = 'walls_footings'
   AND key IN ('labor_forming_sf', 'labor_place_finish_sf', 'labor_wreck_sf', 'labor_rub_patch_sf')
ON CONFLICT (kind, key) DO NOTHING;

-- Should a database's walls kind lack one, the 06-Footings tab's D67:D70.
INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('spot_footings', 'labor_forming_sf',      3.50, '06-Footings D67 (sql/089): per footing face foot'),
    ('spot_footings', 'labor_place_finish_sf', 3.50, '06-Footings D68 (sql/089): per footing face foot'),
    ('spot_footings', 'labor_wreck_sf',        1.00, '06-Footings D69 (sql/089): per footing face foot'),
    ('spot_footings', 'labor_rub_patch_sf',    0.25, '06-Footings D70 (sql/089): per footing face foot')
ON CONFLICT (kind, key) DO NOTHING;

-- The price sheets: the four rates on every estimate that lacks them, at the
-- assembly's value, labelled the way the price book labels them.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', 'spot_footings', r.key,
       CASE r.key WHEN 'labor_forming_sf'      THEN 'Forming labor'
                  WHEN 'labor_place_finish_sf' THEN 'Place & finish labor'
                  WHEN 'labor_wreck_sf'        THEN 'Wreck forms labor'
                  ELSE                              'Rub & patch labor' END,
       'SF', 'spot_footings rates', r.value, r.value
  FROM estimates e
  CROSS JOIN assembly_rates r
 WHERE r.kind = 'spot_footings'
   AND r.key IN ('labor_forming_sf', 'labor_place_finish_sf', 'labor_wreck_sf', 'labor_rub_patch_sf')
   AND NOT EXISTS (
       SELECT 1 FROM estimate_prices p
        WHERE p.estimate_id = e.id AND p.kind = 'assembly_rate'
          AND p.scope = 'spot_footings' AND p.ref_key = r.key);
