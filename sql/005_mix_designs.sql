-- Expand mix_designs + concrete suppliers / prices
-- Source: Pricing tab (Updated Estimate Worksheet) + CONCRETE BIDS mix list
-- Apply: psql -d estimating -f sql/005_mix_designs.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- Expand mix_designs catalog
-- ---------------------------------------------------------------------------
ALTER TABLE mix_designs
    ADD COLUMN IF NOT EXISTS name              text,
    ADD COLUMN IF NOT EXISTS strength_psi      integer,
    ADD COLUMN IF NOT EXISTS has_ash           boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS has_air           boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS sack_count        numeric(4, 1),
    ADD COLUMN IF NOT EXISTS typical_use       text,
    ADD COLUMN IF NOT EXISTS unit              text NOT NULL DEFAULT 'CY',
    ADD COLUMN IF NOT EXISTS sort_order        integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS notes             text,
    ADD COLUMN IF NOT EXISTS updated_at        timestamptz NOT NULL DEFAULT now();

-- Backfill name from description/code where empty
UPDATE mix_designs
SET name = coalesce(nullif(name, ''), description, code)
WHERE name IS NULL;

ALTER TABLE mix_designs
    ALTER COLUMN name SET NOT NULL;

COMMENT ON TABLE mix_designs IS
    'Concrete mix catalog (psi, ash/air, sack, typical use). Unit costs via mix_prices or default_unit_cost.';
COMMENT ON COLUMN mix_designs.unit_cost IS
    'Default/company unit cost $/CY (often from primary supplier); prefer mix_prices for supplier-specific';
COMMENT ON COLUMN mix_designs.code IS
    'Short unique code e.g. 3000-ASH-SOG, 3000-SW';

CREATE INDEX IF NOT EXISTS mix_designs_strength_psi_idx ON mix_designs (strength_psi);
CREATE INDEX IF NOT EXISTS mix_designs_active_idx ON mix_designs (is_active);

-- ---------------------------------------------------------------------------
-- Concrete suppliers (Pricing left column companies)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concrete_suppliers (
    id              serial PRIMARY KEY,
    name            text NOT NULL UNIQUE,
    contact_name    text,
    phone           text,
    notes           text,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE concrete_suppliers IS 'Ready-mix suppliers quoted on Pricing / CONCRETE BIDS';

-- ---------------------------------------------------------------------------
-- Supplier-specific mix unit prices ($/CY)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mix_prices (
    id              serial PRIMARY KEY,
    mix_design_id   integer NOT NULL REFERENCES mix_designs (id) ON DELETE CASCADE,
    supplier_id     integer NOT NULL REFERENCES concrete_suppliers (id) ON DELETE CASCADE,
    unit_cost       numeric(12, 4) NOT NULL,
    price_as_of     date,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (mix_design_id, supplier_id, price_as_of)
);

CREATE INDEX IF NOT EXISTS mix_prices_mix_design_id_idx ON mix_prices (mix_design_id);
CREATE INDEX IF NOT EXISTS mix_prices_supplier_id_idx ON mix_prices (supplier_id);

COMMENT ON TABLE mix_prices IS 'Quoted $/CY by supplier and mix; price_as_of NULL = current undated quote';

-- Allow one "current" row with null price_as_of per mix+supplier
CREATE UNIQUE INDEX IF NOT EXISTS mix_prices_current_uidx
    ON mix_prices (mix_design_id, supplier_id)
    WHERE price_as_of IS NULL;

-- ---------------------------------------------------------------------------
-- Seed / refresh catalog from Pricing headers (Martin Marietta rates)
-- Upsert by code so re-runs are safe
-- ---------------------------------------------------------------------------

-- Deactivate bare placeholder codes if we're replacing with richer codes
-- Keep ids stable for any future FKs: update rows 1-5 in place, insert rest.

UPDATE mix_designs SET
    code = '3000-ASH-SOG',
    name = '3000 PSI W/ ASH PIERS, SOG',
    description = '3000 PSI with fly ash — piers, SOG',
    strength_psi = 3000,
    has_ash = true,
    has_air = false,
    typical_use = 'Piers, grade beams, SOG',
    unit_cost = 155.0000,
    sort_order = 10,
    updated_at = now()
WHERE id = 1;

UPDATE mix_designs SET
    code = '3500',
    name = '3500 PSI',
    description = '3500 PSI',
    strength_psi = 3500,
    has_ash = false,
    has_air = false,
    typical_use = NULL,
    unit_cost = 160.0000,
    sort_order = 20,
    updated_at = now()
WHERE id = 2;

UPDATE mix_designs SET
    code = '4000',
    name = '4000 PSI',
    description = '4000 PSI',
    strength_psi = 4000,
    has_ash = false,
    has_air = false,
    typical_use = NULL,
    unit_cost = 165.0000,
    sort_order = 30,
    updated_at = now()
WHERE id = 3;

UPDATE mix_designs SET
    code = '4500',
    name = '4500 PSI',
    description = '4500 PSI',
    strength_psi = 4500,
    has_ash = false,
    has_air = false,
    typical_use = NULL,
    unit_cost = 170.0000,
    sort_order = 40,
    updated_at = now()
WHERE id = 4;

UPDATE mix_designs SET
    code = '5000',
    name = '5000 PSI',
    description = '5000 PSI',
    strength_psi = 5000,
    has_ash = false,
    has_air = false,
    typical_use = NULL,
    unit_cost = 175.0000,
    sort_order = 50,
    updated_at = now()
WHERE id = 5;

INSERT INTO mix_designs (
    code, name, description, strength_psi, has_ash, has_air, sack_count,
    typical_use, unit, unit_cost, sort_order, is_active
) VALUES
    (
        '3000-SW',
        '3000 PSI Sidewalk and Hardscape',
        '3000 PSI sidewalk / hardscape',
        3000, false, false, NULL,
        'Sidewalks, hardscape',
        'CY', 155.0000, 60, true
    ),
    (
        '3000-4.5SK-SW',
        '3000 PSI / 4.5 SACK SIDE WALKS',
        'From CONCRETE BIDS form',
        3000, false, false, 4.5,
        'Sidewalks',
        'CY', NULL, 70, true
    ),
    (
        '3000-5SK-STRUCT',
        '3000 PSI 5 SACK PIERS GRADE BEAMS SOG PAVING',
        'From CONCRETE BIDS form',
        3000, false, false, 5.0,
        'Piers, grade beams, SOG, paving',
        'CY', NULL, 80, true
    ),
    (
        '4000-EL-DECK',
        '4000 PSI EL. DECK',
        'Elevated deck — CONCRETE BIDS form',
        4000, false, false, NULL,
        'Elevated deck',
        'CY', NULL, 90, true
    ),
    (
        '5000-BEAMS-WALLS',
        '5000 PSI BEAMS AND WALLS',
        'Beams and walls — CONCRETE BIDS form',
        5000, false, false, NULL,
        'Beams, walls',
        'CY', NULL, 100, true
    )
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    strength_psi = EXCLUDED.strength_psi,
    has_ash = EXCLUDED.has_ash,
    has_air = EXCLUDED.has_air,
    sack_count = EXCLUDED.sack_count,
    typical_use = EXCLUDED.typical_use,
    unit_cost = COALESCE(EXCLUDED.unit_cost, mix_designs.unit_cost),
    sort_order = EXCLUDED.sort_order,
    is_active = true,
    updated_at = now();

-- Supplier seed (workbook spelling "Martin Marrieta")
INSERT INTO concrete_suppliers (name, contact_name, notes)
VALUES
    ('Martin Marietta', 'Justin', 'Pricing tab; workbook sometimes spells Marrieta'),
    ('SRM', NULL, 'Seen on SOG/Paving Pricing (older workbook)'),
    ('Argos', NULL, 'Mentioned as blanket price on SOG Pricing')
ON CONFLICT (name) DO UPDATE SET
    contact_name = COALESCE(EXCLUDED.contact_name, concrete_suppliers.contact_name),
    notes = COALESCE(EXCLUDED.notes, concrete_suppliers.notes),
    updated_at = now();

-- Martin Marietta prices for primary Pricing mixes (undated current quote)
INSERT INTO mix_prices (mix_design_id, supplier_id, unit_cost, price_as_of, notes)
SELECT m.id, s.id, m.unit_cost, NULL, 'From Pricing tab — Updated Estimate Worksheet'
FROM mix_designs m
CROSS JOIN concrete_suppliers s
WHERE s.name = 'Martin Marietta'
  AND m.code IN ('3000-ASH-SOG', '3500', '4000', '4500', '5000', '3000-SW')
  AND m.unit_cost IS NOT NULL
ON CONFLICT (mix_design_id, supplier_id) WHERE price_as_of IS NULL
DO UPDATE SET
    unit_cost = EXCLUDED.unit_cost,
    notes = EXCLUDED.notes,
    updated_at = now();

COMMIT;
