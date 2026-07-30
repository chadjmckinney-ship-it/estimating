-- Equipment rental catalog from Pricing tab
-- Primary: New Current Worksheet (EQUIPMENT RENTAL section)
-- Extra: Concrete Pumping + Compactor from Updated Estimate Worksheet
-- Apply: psql -d estimating -f sql/008_equipment.sql

BEGIN;

CREATE TABLE IF NOT EXISTS equipment (
    id              serial PRIMARY KEY,
    code            text UNIQUE,
    name            text NOT NULL,
    category        text NOT NULL DEFAULT 'other'
                    CHECK (category IN (
                        'earthwork',
                        'lifting',
                        'power',
                        'hauling',
                        'pumping',
                        'other'
                    )),
    unit            text NOT NULL DEFAULT 'DAY',  -- DAY, YD, HOUR, etc.
    unit_cost       numeric(12, 4),
    unit_note       text,
    description     text,
    is_owned        boolean NOT NULL DEFAULT false, -- company-owned vs rental rate
    is_active       boolean NOT NULL DEFAULT true,
    sort_order      integer NOT NULL DEFAULT 0,
    source_sheet    text DEFAULT 'Pricing',
    source_row      integer,
    price_as_of     date,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name, unit)
);

CREATE INDEX IF NOT EXISTS equipment_category_idx ON equipment (category);
CREATE INDEX IF NOT EXISTS equipment_active_idx ON equipment (is_active);
CREATE INDEX IF NOT EXISTS equipment_name_idx ON equipment (name);

COMMENT ON TABLE equipment IS
    'Equipment rental / use rates from Pricing EQUIPMENT RENTAL section';
COMMENT ON COLUMN equipment.unit_cost IS 'Default rate (usually $/DAY; pumping may be $/YD)';
COMMENT ON COLUMN equipment.is_owned IS 'True if company-owned unit (rate may be internal cost)';

-- Seed from New Current Worksheet.xlsm Pricing rows 32–45
INSERT INTO equipment (
    code, name, category, unit, unit_cost, sort_order,
    source_sheet, source_row, price_as_of
) VALUES
    ('SKYTRACK',        'SkyTrack',                 'lifting',   'DAY',  425.0000,  10,
     'Pricing (New Current Worksheet)', 32, NULL),
    ('MINI-EXCAVATOR',  'MINI EXCAVATOR',           'earthwork', 'DAY',  475.0000,  20,
     'Pricing (New Current Worksheet)', 33, NULL),
    ('TRENCHER',        'TRENCHER',                 'earthwork', 'DAY',  325.0000,  30,
     'Pricing (New Current Worksheet)', 34, NULL),
    ('SKID-STEER',      'SKID STEER',               'earthwork', 'DAY',  325.0000,  40,
     'Pricing (New Current Worksheet)', 35, NULL),
    ('BOXBLADE',        'BOXBLADE',                 'earthwork', 'DAY',  350.0000,  50,
     'Pricing (New Current Worksheet)', 36, NULL),
    ('CHIPPING-HAMMER', 'CHIPPING HAMMER',          'power',     'DAY',   45.0000,  60,
     'Pricing (New Current Worksheet)', 37, NULL),
    ('COMPRESSOR',      'COMPRESSOR',               'power',     'DAY',  100.0000,  70,
     'Pricing (New Current Worksheet)', 38, NULL),
    ('TOWER-LIGHT',     'TOWER LIGHT w/ GENERATOR', 'power',     'DAY',  100.0000,  80,
     'Pricing (New Current Worksheet)', 39, NULL),
    ('GENERATOR',       'GENERATOR',                'power',     'DAY',   32.0000,  90,
     'Pricing (New Current Worksheet)', 40, NULL),
    ('SKY-LIFT',        'SKY LIFT',                 'lifting',   'DAY',  380.0000, 100,
     'Pricing (New Current Worksheet)', 41, NULL),
    ('CRANE-OPERATOR',  'CRANE AND OPERATOR',       'lifting',   'DAY', 2400.0000, 110,
     'Pricing (New Current Worksheet)', 42, NULL),
    ('DUMPTRUCK-5-6YD', '5-6 YD Dumptruck',         'hauling',   'DAY',  240.0000, 120,
     'Pricing (New Current Worksheet)', 43, NULL),
    ('BACKHOE',         'BACK HOE',                 'earthwork', 'DAY',  425.0000, 130,
     'Pricing (New Current Worksheet)', 44, NULL),
    ('WATER-TRUCK',     'Water Truck',              'hauling',   'DAY',  450.0000, 140,
     'Pricing (New Current Worksheet)', 45, NULL),
    -- Also on older Whitecap Pricing (useful rates not on New Current list)
    ('CONCRETE-PUMP',   'Concrete Pumping',         'pumping',   'YD',    16.0000, 150,
     'Pricing (Updated Estimate Worksheet)', 41, NULL),
    ('COMPACTOR',       'COMPACTOR',                'earthwork', 'DAY',  200.0000, 160,
     'Pricing (Updated Estimate Worksheet)', 42, NULL)
ON CONFLICT (name, unit) DO UPDATE SET
    code = COALESCE(EXCLUDED.code, equipment.code),
    category = EXCLUDED.category,
    unit_cost = EXCLUDED.unit_cost,
    sort_order = EXCLUDED.sort_order,
    source_sheet = EXCLUDED.source_sheet,
    source_row = EXCLUDED.source_row,
    is_active = true,
    updated_at = now();

COMMIT;
