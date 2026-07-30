-- Rebuild mix catalog:
--   {PSI} PSI - SC
--   {PSI} PSI - ASH
--   {PSI} PSI - Air - ASH
-- for 3000 / 3500 / 4000 / 4500 / 5000
-- plus 3000 PSI - Integral Color
--
-- Apply: psql -d estimating -f sql/006_mix_designs_sc_ash_air.sql

BEGIN;

-- No mono_slab refs expected; clear prices then redesigns
DELETE FROM mix_prices;
DELETE FROM mix_designs;
ALTER SEQUENCE mix_designs_id_seq RESTART WITH 1;

-- SC = straight cement (no ash, no air)
-- ASH = fly ash, no air
-- Air - ASH = air entrained + fly ash

INSERT INTO mix_designs (
    code, name, description,
    strength_psi, has_ash, has_air, sack_count,
    typical_use, unit, unit_cost, sort_order, is_active
) VALUES
    -- 3000
    ('3000-SC',       '3000 PSI - SC',
     '3000 PSI straight cement (no ash, no air)',
     3000, false, false, NULL, NULL, 'CY', NULL, 10, true),
    ('3000-ASH',      '3000 PSI - ASH',
     '3000 PSI with fly ash',
     3000, true,  false, NULL, NULL, 'CY', NULL, 20, true),
    ('3000-AIR-ASH',  '3000 PSI - Air - ASH',
     '3000 PSI air entrained with fly ash',
     3000, true,  true,  NULL, NULL, 'CY', NULL, 30, true),
    ('3000-INT-COLOR','3000 PSI - Integral Color',
     '3000 PSI with integral color',
     3000, false, false, NULL, 'Integral color', 'CY', NULL, 40, true),

    -- 3500
    ('3500-SC',       '3500 PSI - SC',
     '3500 PSI straight cement (no ash, no air)',
     3500, false, false, NULL, NULL, 'CY', NULL, 50, true),
    ('3500-ASH',      '3500 PSI - ASH',
     '3500 PSI with fly ash',
     3500, true,  false, NULL, NULL, 'CY', NULL, 60, true),
    ('3500-AIR-ASH',  '3500 PSI - Air - ASH',
     '3500 PSI air entrained with fly ash',
     3500, true,  true,  NULL, NULL, 'CY', NULL, 70, true),

    -- 4000
    ('4000-SC',       '4000 PSI - SC',
     '4000 PSI straight cement (no ash, no air)',
     4000, false, false, NULL, NULL, 'CY', NULL, 80, true),
    ('4000-ASH',      '4000 PSI - ASH',
     '4000 PSI with fly ash',
     4000, true,  false, NULL, NULL, 'CY', NULL, 90, true),
    ('4000-AIR-ASH',  '4000 PSI - Air - ASH',
     '4000 PSI air entrained with fly ash',
     4000, true,  true,  NULL, NULL, 'CY', NULL, 100, true),

    -- 4500
    ('4500-SC',       '4500 PSI - SC',
     '4500 PSI straight cement (no ash, no air)',
     4500, false, false, NULL, NULL, 'CY', NULL, 110, true),
    ('4500-ASH',      '4500 PSI - ASH',
     '4500 PSI with fly ash',
     4500, true,  false, NULL, NULL, 'CY', NULL, 120, true),
    ('4500-AIR-ASH',  '4500 PSI - Air - ASH',
     '4500 PSI air entrained with fly ash',
     4500, true,  true,  NULL, NULL, 'CY', NULL, 130, true),

    -- 5000
    ('5000-SC',       '5000 PSI - SC',
     '5000 PSI straight cement (no ash, no air)',
     5000, false, false, NULL, NULL, 'CY', NULL, 140, true),
    ('5000-ASH',      '5000 PSI - ASH',
     '5000 PSI with fly ash',
     5000, true,  false, NULL, NULL, 'CY', NULL, 150, true),
    ('5000-AIR-ASH',  '5000 PSI - Air - ASH',
     '5000 PSI air entrained with fly ash',
     5000, true,  true,  NULL, NULL, 'CY', NULL, 160, true);

COMMENT ON TABLE mix_designs IS
    'Concrete mix catalog: {PSI} PSI - SC | ASH | Air - ASH; plus 3000 PSI - Integral Color';

COMMIT;
