-- Labor + supervision takeoff for mono slab estimates (Excel 04 LABOR / SUPERVISION)
-- Apply: psql -d estimating -f sql/018_estimate_labor.sql

BEGIN;

CREATE TABLE IF NOT EXISTS estimate_labor_lines (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    group_name      text NOT NULL CHECK (group_name IN ('labor', 'supervision')),
    code            text NOT NULL,
    label           text NOT NULL,
    enabled         boolean NOT NULL DEFAULT true,  -- Excel Y/N (sub / in-house)
    rate            numeric(12, 4) NOT NULL DEFAULT 0,
    unit            text NOT NULL,                 -- /SF, /TON, /DAY, EA, …
    qty             numeric(14, 4) NOT NULL DEFAULT 0,
    ext_cost        numeric(14, 2) NOT NULL DEFAULT 0,
    formula         text,
    notes           text,
    sort_order      integer NOT NULL DEFAULT 0,
    is_manual       boolean NOT NULL DEFAULT false, -- keep rate/qty on refresh if true
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (estimate_id, code)
);

CREATE INDEX IF NOT EXISTS estimate_labor_lines_estimate_id_idx
    ON estimate_labor_lines (estimate_id);

COMMENT ON TABLE estimate_labor_lines IS
    'Slab labor + supervision lines (Excel 04). Qty from pours; rates editable.';

CREATE TABLE IF NOT EXISTS estimate_labor_summary (
    estimate_id         uuid PRIMARY KEY REFERENCES estimates (id) ON DELETE CASCADE,
    pour_count          integer NOT NULL DEFAULT 0,
    total_sf            numeric(14, 3) NOT NULL DEFAULT 0,
    drops_ff            numeric(14, 3) NOT NULL DEFAULT 0,
    total_rebar_lb      numeric(14, 3) NOT NULL DEFAULT 0,
    total_rebar_tons    numeric(14, 4) NOT NULL DEFAULT 0,
    super_weeks         numeric(12, 4) NOT NULL DEFAULT 0,
    super_days          numeric(12, 4) NOT NULL DEFAULT 0,
    total_labor_cost    numeric(14, 2) NOT NULL DEFAULT 0,
    total_supervision_cost numeric(14, 2) NOT NULL DEFAULT 0,
    total_cost          numeric(14, 2) NOT NULL DEFAULT 0,
    cost_per_sf         numeric(12, 4),
    refreshed_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE estimate_labor_summary IS
    'Last labor/supervision rollup for an estimate';

-- Default rates (company) — overridable per estimate line
INSERT INTO system_settings (key, value, description) VALUES
    ('labor_forming_sf', '0.45'::jsonb, 'Slab labor: Forming $/SF'),
    ('labor_grading_sf', '0.70'::jsonb, 'Slab labor: Grading/cables $/SF'),
    ('labor_place_finish_sf', '0.55'::jsonb, 'Slab labor: Place and finish $/SF'),
    ('labor_wreck_sf', '0.20'::jsonb, 'Slab labor: Wreck and clean up $/SF'),
    ('labor_drops_ff', '8'::jsonb, 'Slab labor: Drops $/FF (face ft)'),
    ('labor_excavation_cy', '12'::jsonb, 'Slab labor: Excavation add $/CY'),
    ('labor_hold_down_ea', '100'::jsonb, 'Slab labor: Hold downs $/EA'),
    ('labor_tie_steel_ton', '450'::jsonb, 'Slab labor: Tie steel $/TON'),
    ('labor_super_sf_per_week', '16000'::jsonb, 'Supervision: SF per superintendent week'),
    ('labor_super_days_per_week', '7'::jsonb, 'Supervision: days per week'),
    ('labor_super_day_rate', '425'::jsonb, 'Supervision: Superintendent $/day'),
    ('labor_foreman_day_rate', '250'::jsonb, 'Supervision: Foreman $/day'),
    ('labor_expense_day_rate', '100'::jsonb, 'Supervision: Expense allowance $/day'),
    ('labor_pm_day_rate', '200'::jsonb, 'Supervision: Project management $/day')
ON CONFLICT (key) DO NOTHING;

COMMIT;
