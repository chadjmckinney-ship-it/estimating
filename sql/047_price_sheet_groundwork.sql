-- 047 — groundwork for the estimate price sheet (stage 0)
--
-- See claude/estimate-price-sheet-spec.md. Every decision here is Chad's,
-- 2026-09-02, and each block below cites the one it carries out.
--
-- Nothing in this file changes a number on any existing estimate. That is
-- the acceptance test for the whole stage and it is asserted in
-- tests/test_stage0_groundwork.py.

-- ---------------------------------------------------------------------------
-- 1. Drop mix_prices and supplier_bids.
--
-- Decision 1: "I like having a master list of rough mix prices that we get
-- from suppliers that we update as we get them, then as we start an estimate,
-- it pulls those numbers."  That is ONE master price per mix — which is
-- mix_designs.unit_cost, and always was. mix_prices was built (sql/005) as a
-- per-supplier, effective-dated history, orphaned by sql/006, and has been
-- empty since. Its only reader ignored price_as_of entirely and took min()
-- across every row, so a 2019 quote would have won on price the day anyone
-- added a second one. A landmine, removed.
--
-- supplier_bids has had no reader since section_quotes replaced it (sql/039).
-- The variance view on top of it goes with it.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS supplier_bid_variance;
DROP TABLE IF EXISTS supplier_bids;
DROP TABLE IF EXISTS mix_prices;

-- concrete_suppliers stays: harmless reference data, and the natural thing to
-- name in a price-sheet note ("SRM, quoted 9/1").

-- ---------------------------------------------------------------------------
-- 2. The last *_unit_cost row in assembly_rates.
--
-- Decision 4. sql/044 deleted ('paving','accessories_unit_cost') as a typed-
-- over workbook cell contradicting the catalog's $0.04 and missed the sidewalk
-- twin. Chad: "think that was again someone edited a formula in the workbook
-- and wasnt caught till we used the excel workbook to build this." Sidewalk
-- now prices accessories from the catalog, like everything else.
-- ---------------------------------------------------------------------------
DELETE FROM assembly_rates
 WHERE kind = 'sidewalk' AND key = 'accessories_unit_cost';

-- ---------------------------------------------------------------------------
-- 3. Four prices that lived in Python.
--
-- forming.py priced these lines from `sheet_unit_cost` literals because the
-- catalog had no row for them to land on. A price in source is a price in a
-- migration by another name (claude/design-decisions.md, "A price comes from
-- the catalog"), and the price sheet cannot pull what the catalog does not
-- hold. Same promotion sql/044 gave FRENCH DRAIN and WATER STOP.
--
-- CONCRETE HAUL OFF: the piers and walls sheets compute loads at $250; the
-- paving sheet types $500 on a manual line that defaults to zero loads. One
-- catalog row, at the figure two of three sheets agree on — the paving figure
-- is flagged in the report, and the price sheet exists precisely so a paving
-- job can carry $500 without a second catalog item.
-- ---------------------------------------------------------------------------
INSERT INTO materials (name, category, unit, unit_cost, unit_note, price_as_of, sort_order)
VALUES
    ('CONCRETE HAUL OFF', 'site_accessories', 'LOAD', 250.0000,
     'Per load hauled — 01-Piers / 06-Walls; the paving sheet typed 500', '2026-09-02', 710),
    ('TEXTURE COMB',      'site_accessories', 'EA',   200.0000,
     'Broom/texture comb — 10-PAVING U-block',                            '2026-09-02', 711),
    ('DOWEL BASKETS',     'structural_accessories', 'LF', 5.2500,
     'Dowel basket assembly per LF — 10-PAVING',                         '2026-09-02', 712),
    ('PIPE BRACING',      'form_accessories', 'EA',   15.0000,
     'Wall form pipe brace, each — 06-Walls',                            '2026-09-02', 713)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. A section knows what it could not price.
--
-- Decision 5: "I dont like concrete prices starting @ $0." A NULL master price
-- used to multiply through as zero and vanish into the total — a fresh install
-- bid $324k of LBJ concrete at nothing with a green suite. costing now names
-- every item it reached for that had no price, and the list is stored beside
-- the totals it qualifies. Empty means every price on this section was real.
-- ---------------------------------------------------------------------------
ALTER TABLE estimate_sections
    ADD COLUMN IF NOT EXISTS calc_unpriced jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN estimate_sections.calc_unpriced IS
    'Items this section reached for that the master list has no price for, '
    'written by refresh_pour_costs. Non-empty = the total is light by an '
    'unknown amount. A NULL price is unpriced, never free (sql/047).';

-- Each stored equipment line remembers where its rate came from. Forming can
-- derive "unpriced" from a NULL unit_cost; a rental priced from a code default
-- has a perfectly plausible NON-null rate, so the source has to be kept.
ALTER TABLE estimate_equipment_lines
    ADD COLUMN IF NOT EXISTS price_source text;
