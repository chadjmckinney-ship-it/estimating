-- Equipment takeoff for mono slab estimates (Excel 04 EQUIPMENT)
-- Apply: psql -d estimating -f sql/019_estimate_equipment.sql

BEGIN;

CREATE TABLE IF NOT EXISTS estimate_equipment_lines (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    group_name      text NOT NULL DEFAULT 'equipment'
                    CHECK (group_name IN ('equipment', 'contract')),
    code            text NOT NULL,
    label           text NOT NULL,
    enabled         boolean NOT NULL DEFAULT true,
    equipment_id    integer REFERENCES equipment (id) ON DELETE SET NULL,
    days_qty        numeric(14, 4) NOT NULL DEFAULT 0,  -- rental days (or CY for pump)
    rate            numeric(12, 4) NOT NULL DEFAULT 0,  -- $/day or $/CY
    unit            text NOT NULL DEFAULT 'DAY',
    billable_units  numeric(14, 4) NOT NULL DEFAULT 0,  -- after rental tier
    ext_cost        numeric(14, 2) NOT NULL DEFAULT 0,
    formula         text,
    notes           text,
    sort_order      integer NOT NULL DEFAULT 0,
    is_manual       boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (estimate_id, code)
);

CREATE INDEX IF NOT EXISTS estimate_equipment_lines_estimate_id_idx
    ON estimate_equipment_lines (estimate_id);

COMMENT ON TABLE estimate_equipment_lines IS
    'Equipment + contract services on an estimate (Excel 04). Days from super duration ladder.';

CREATE TABLE IF NOT EXISTS estimate_equipment_summary (
    estimate_id         uuid PRIMARY KEY REFERENCES estimates (id) ON DELETE CASCADE,
    pour_count          integer NOT NULL DEFAULT 0,
    total_sf            numeric(14, 3) NOT NULL DEFAULT 0,
    super_days          numeric(12, 4) NOT NULL DEFAULT 0,
    equip_days          numeric(12, 4) NOT NULL DEFAULT 0,  -- ladder days for day-rate fleet
    total_concrete_cy   numeric(14, 4) NOT NULL DEFAULT 0,
    total_equipment_cost numeric(14, 2) NOT NULL DEFAULT 0,
    total_contract_cost numeric(14, 2) NOT NULL DEFAULT 0,
    total_cost          numeric(14, 2) NOT NULL DEFAULT 0,
    cost_per_sf         numeric(12, 4),
    refreshed_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE estimate_equipment_summary IS
    'Last equipment takeoff rollup for an estimate';

-- Seed vault / misc day rates if not in catalog as equipment rows (optional lines)
INSERT INTO system_settings (key, value, description) VALUES
    ('equip_vault_day_rate', '25'::jsonb, 'Vault rental $/day (Excel EQUIPMENT)'),
    ('equip_misc_day_rate', '55'::jsonb, 'Miscellaneous equipment $/day'),
    ('equip_use_rental_tiers', 'true'::jsonb,
     'If true, bill day-rate gear with Excel week/month tier formula; else days × rate')
ON CONFLICT (key) DO NOTHING;

COMMIT;
