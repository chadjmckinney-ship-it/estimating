-- 044: a price lives in the catalog. assembly_rates names a RULE, not a price.
--
-- `claude/design-decisions.md` already says this — "A price comes from the
-- catalog; the assembly says which item, or states a rate" — and the
-- implementation had drifted from it in seventeen places. Every one of those
-- rows was copied out of a workbook cell by sql/035–040, which means the app
-- froze a 2002-era keystroke into a migration file and then reproduced it
-- faithfully for weeks.
--
-- sql/043 removed the worst of them (piers rebar at $0.75, which turned out to
-- be a typed-over Pricing lookup, not a pier premium). This finishes the job.
--
-- Chad's framing, 2026-09-01: *"a bad place to store pricing as it changes
-- monthly so in a year.. it can be way off."*
--
-- ---------------------------------------------------------------------------
-- 1. DEAD ROWS. Seeded with a price, read by no code, and authoritative-looking
--    to anyone who greps the table. `_assembly_unit_cost` builds its key as
--    `<code>_unit_cost`, so a row named `chamfer_lf_cost` was never going to be
--    found; bells price as concrete CY, so `pier_bell_cost_per_in` never had a
--    reader either. Same class as the `pier_drill_quote` column that existed in
--    a migration and was read by nothing (sql/038).

DELETE FROM assembly_rates WHERE (kind, key) IN (
    ('walls_footings', 'chamfer_lf_cost'),        -- code looks up chamfer_unit_cost
    ('walls_footings', 'french_drain_lf_cost'),   -- code looks up french_drain_unit_cost
    ('walls_footings', 'water_stop_lf_cost'),     -- code looks up water_stop_unit_cost
    ('piers',          'pier_bell_cost_per_in')   -- bells are priced as CY
);

-- ---------------------------------------------------------------------------
-- 2. EXACT DUPLICATES of a catalog item. Same number in two places, which is
--    one place too many: whichever moves first, the other silently disagrees.
--    Deleting these changes nothing today and stops that drift.
--
--      piers/walls accessories 0.04 = materials.ACCESSORIES 0.04
--      paving  bobcat  325          = equipment.SKID STEER 325   (Pricing!D35)
--      *       light tower 100      = equipment.TOWER LIGHT w/ GENERATOR 100

DELETE FROM assembly_rates WHERE (kind, key) IN (
    ('piers',          'accessories_unit_cost'),
    ('walls_footings', 'accessories_unit_cost'),
    ('paving',         'equip_bobcat_day_rate'),
    ('piers',          'equip_light_tower_day_rate'),
    ('walls_footings', 'equip_light_tower_day_rate'),
    ('paving',         'equip_light_tower_day_rate')
);

-- ---------------------------------------------------------------------------
-- 3. STALE COPIES. These DIFFER from the catalog, and each was read as a real
--    assembly-specific price until 2026-09-01. Both turned out to be
--    typed-over lookups in the workbook, and Chad's own `Pricing` sheet
--    disagrees with both:
--
--      walls sand      $20.00  ← `06-Walls!F59` typed;  Pricing!D19 = $25.00
--      paving accessor  $0.02  ← `10-PAVING!T80` typed; Pricing!Q14 = $0.04
--
--    THESE MOVE MONEY. On LBJ: walls +$2,078.40, paving +$3,255.87 (with tax).
--    Chad's call, on the evidence of his own price sheet.

DELETE FROM assembly_rates WHERE (kind, key) IN (
    ('walls_footings', 'sand_unit_cost'),
    ('paving',         'accessories_unit_cost')
);

-- ---------------------------------------------------------------------------
-- 4. Two real purchased materials that had no catalog item, so the only way to
--    reprice them was to edit a migration. The walls line set already reaches
--    for them by name and falls through to `sheet_unit_cost` — priced at the
--    workbook's figure and honestly labelled `price_source: "sheet"`. Giving
--    them catalog rows changes no number today and makes them editable in the
--    app like everything else.
--
--    Neither exists on the `Pricing` sheet either (`06-Walls!U67` and `U69`
--    are typed constants) — worth adding there too.

INSERT INTO materials (name, category, unit, unit_cost, unit_note, price_as_of, sort_order)
VALUES
    ('FRENCH DRAIN', 'site_accessories', 'LF', 8.5000,
     'Pipe, sock and gravel per LF — 06-Walls U69', '2026-09-01', 700),
    ('WATER STOP',   'site_accessories', 'LF', 1.0000,
     'Per LF of wall — 06-Walls U67',               '2026-09-01', 701)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- What SURVIVES here, and why it is not a price:
--
--   equip_vault_day_rate      50 / 15   a jobsite storage charge; no catalog item
--   equip_misc_day_rate       35        an allowance, not a machine
--   out_of_town_day_rate      250 / 200 a per-diem
--
-- Those are genuine assembly rules. The test for the difference: if the catalog
-- could carry it, the catalog should.
