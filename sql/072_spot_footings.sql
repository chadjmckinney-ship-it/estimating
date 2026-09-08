-- 072_spot_footings.sql
--
-- Spot footings: a section of their own, on the walls engine.
--
-- Chad, 2026-09-07: "most spread footings have a weld plate.. so I think we
-- need a section for spread footings and one for continuous footings.. we can
-- do cont footings when we do grade beams.. for spot footings, the wall calc
-- works if we do l w and h with a count.. t&b mats"
--
-- The workbook agrees with him: 06-Footings is the walls tab with the wall
-- columns left blank. On the Pearl Landing Podium estimate it carries four
-- pad footing types entered as a count times a size — E10 = B10 * 10 — and
-- prices at $187,680.06 through the same lumber block, the same FOOTINGS
-- $/SF labor line, the same tie steel, excavation and equipment ladder the
-- walls section already reproduces. Built as a walls section with the wall
-- blank, the app matched that tab line for line before this migration
-- existed; what it lacked was a row shaped like a footing.
--
-- So: a new kind, spot_footings, in WALL_KINDS everywhere the engine
-- branches; three columns on wall_runs — the count, the length of each, and
-- whether the footing carries a weld plate — with the run's length derived
-- as count x each the way the sheet does it; the walls tab's rates copied
-- for the new kind (the sheet is the same tab); WELD PLATE as a catalog
-- material with no price yet, so the line reports unpriced rather than free
-- until Chad names one on the materials screen; and the new kind's rates on
-- every job's price sheet, so no job reads them as unpriced until its next
-- pull. Continuous footings wait for grade beams.

-- The kind.
ALTER TABLE estimate_sections DROP CONSTRAINT IF EXISTS estimate_sections_kind_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_kind_check CHECK (kind IN (
        'mono_slab', 'paving', 'sidewalk', 'piers', 'grade_beams',
        'walls_footings', 'spot_footings', 'columns', 'slabs', 'cip_deck',
        'slab_on_deck', 'panels', 'miscellaneous'
    ));

-- A spot footing on a wall run: the count, the length of each, the plate.
ALTER TABLE wall_runs ADD COLUMN IF NOT EXISTS footing_count integer NOT NULL DEFAULT 1;
ALTER TABLE wall_runs ADD COLUMN IF NOT EXISTS footing_each_ft numeric(12, 3);
ALTER TABLE wall_runs ADD COLUMN IF NOT EXISTS weld_plate boolean NOT NULL DEFAULT false;
ALTER TABLE wall_runs DROP CONSTRAINT IF EXISTS wall_runs_footing_count_check;
ALTER TABLE wall_runs ADD CONSTRAINT wall_runs_footing_count_check CHECK (footing_count >= 0);
COMMENT ON COLUMN wall_runs.footing_count IS
    'Spot footings (sql/072): how many of this type. 1 on a wall run.';
COMMENT ON COLUMN wall_runs.footing_each_ft IS
    'Spot footings (sql/072): the length of each; length_ft = footing_count x footing_each_ft, the sheet''s E = B x size. NULL on a wall run.';
COMMENT ON COLUMN wall_runs.weld_plate IS
    'Spot footings (sql/072): one WELD PLATE per footing, priced from the catalog.';

-- The rates: the sheet is the walls tab, so the new kind reads what walls
-- reads — less the four form-foot labor lines and the french drain, which a
-- footing without a wall never builds and whose rates would otherwise sit on
-- its rate sheet pretending to be read.
INSERT INTO assembly_rates (kind, key, value, note)
SELECT 'spot_footings', key, value, 'copied from walls_footings (sql/072): 06-Footings is the walls tab'
  FROM assembly_rates
 WHERE kind = 'walls_footings'
   AND key NOT IN ('labor_forming_sf', 'labor_place_finish_sf', 'labor_wreck_sf',
                   'labor_rub_patch_sf', 'labor_french_drain_lf')
ON CONFLICT (kind, key) DO NOTHING;

-- The plate. No price until Chad names one: unpriced, not free.
INSERT INTO materials (name, category, unit, unit_cost, description, is_active, sort_order)
SELECT 'WELD PLATE', 'structural_accessories', 'EA', NULL,
       'Embedded plate at a spot footing for the column above (sql/072). Price it on the materials screen.',
       true, 0
 WHERE NOT EXISTS (SELECT 1 FROM materials WHERE upper(name) = 'WELD PLATE');

-- The price sheets: the new kind's rates, at the walls values already on each sheet.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT p.estimate_id, p.kind, 'spot_footings', p.ref_key, p.label, p.unit,
       'spot_footings rates', p.catalog_value, p.catalog_value
  FROM estimate_prices p
 WHERE p.kind = 'assembly_rate' AND p.scope = 'walls_footings'
   AND p.ref_key NOT IN ('labor_forming_sf', 'labor_place_finish_sf', 'labor_wreck_sf',
                         'labor_rub_patch_sf', 'labor_french_drain_lf')
ON CONFLICT DO NOTHING;
