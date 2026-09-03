-- Per-pour cost / sale / SF-CY and per-estimate markup (sql/026).
--
-- Engines keep showing cost; margin + contingency live on the bid. SALE =
-- cost × (1 + margin_pct + contingency_pct). Defaults 20% / 3%. No tax.
--
-- Pour COST = direct materials priced from stored quantities × catalog unit
-- costs, plus this pour's share of ON forming / labor / supervision /
-- equipment lines (SF share by default; CY-driven lines such as pumping by
-- CY share). Off lines (sky track) stay $0.
--
-- Stored, not live-on-read. Recalc rewrites these columns:
--   POST /api/estimates/{id}/recalc
--
-- Apply: psql -d estimating -f sql/026_pour_cost_sale.sql

BEGIN;

ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS margin_pct numeric(6, 4) NOT NULL DEFAULT 0.20;
ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS contingency_pct numeric(6, 4) NOT NULL DEFAULT 0.03;
ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS calc_total_cost numeric(14, 2);
ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS calc_total_sale numeric(14, 2);
ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS calc_cost_per_sf numeric(12, 4);
ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS calc_sale_per_sf numeric(12, 4);

ALTER TABLE estimates DROP CONSTRAINT IF EXISTS estimates_margin_pct_check;
ALTER TABLE estimates
    ADD CONSTRAINT estimates_margin_pct_check
    CHECK (margin_pct >= 0 AND margin_pct <= 2);

ALTER TABLE estimates DROP CONSTRAINT IF EXISTS estimates_contingency_pct_check;
ALTER TABLE estimates
    ADD CONSTRAINT estimates_contingency_pct_check
    CHECK (contingency_pct >= 0 AND contingency_pct <= 2);

COMMENT ON COLUMN estimates.margin_pct IS
    'Bid markup as a decimal (0.20 = 20%). SALE = cost × (1 + margin + contingency).';
COMMENT ON COLUMN estimates.contingency_pct IS
    'Bid contingency as a decimal (0.03 = 3%). Editable on the estimate; not hardcoded in the pour formula.';
COMMENT ON COLUMN estimates.calc_total_cost IS
    'Stored sum of pour calc_cost from the last recost. Ties to the same rules as the pours.';
COMMENT ON COLUMN estimates.calc_total_sale IS
    'Stored sum of pour calc_sale from the last recost.';

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_sf_per_cy numeric(14, 4);
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_direct_cost numeric(14, 2);
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_allocated_cost numeric(14, 2);
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_cost numeric(14, 2);
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_sale numeric(14, 2);
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_cost_per_sf numeric(12, 4);
ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_sale_per_sf numeric(12, 4);

COMMENT ON COLUMN mono_slabs.calc_sf_per_cy IS
    'Pour SF / total concrete CY (slab + GB/exposed/drop). NULL when CY is 0.';
COMMENT ON COLUMN mono_slabs.calc_direct_cost IS
    'Direct materials on this pour: mix, sand, rebar, PT, poly, mesh from stored qty × catalog.';
COMMENT ON COLUMN mono_slabs.calc_allocated_cost IS
    'This pour''s share of ON estimate takeoff lines (forming / labor / equipment).';
COMMENT ON COLUMN mono_slabs.calc_cost IS
    'direct + allocated. Engines show cost; markup is applied on the bid.';
COMMENT ON COLUMN mono_slabs.calc_sale IS
    'cost × (1 + estimate.margin_pct + estimate.contingency_pct).';

COMMIT;