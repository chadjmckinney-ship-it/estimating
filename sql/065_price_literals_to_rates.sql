-- 065_price_literals_to_rates.sql
--
-- Three prices that lived as literals in services/estimate_equipment.py
-- become rates on the ladder, so they sit on the price sheet with everything
-- else and a job can edit them without a code change (audit 2026-09-04, P3;
-- batch 1 on Chad's "yes, start batch 1", 2026-09-06).
--
--   * MISCELLANEOUS contract on piers and walls: `rate=1000` in the code. Now
--     misc_contract_ls, a company setting at $1,000 (quantity 0 until typed).
--   * HAUL OFF on the mono slab: `Decimal("12.5000")` in the code. Now the
--     slab's own assembly rate on haul_off_cy, the key piers ($4) and columns
--     ($6) already read.
--   * ENGINEERING on the mono slab: `Decimal("0.2000")` in the code, off by
--     default. Now the slab's assembly rate on engineering_sf, the key piers
--     reads at $1.05.
--
-- Same numbers, same lines; only where they live. The walls SKY TRACK line's
-- rate key moved in the code alone (it read the fork truck's key).

INSERT INTO system_settings (key, value, description) VALUES
    ('misc_contract_ls', '1000'::jsonb,
     'MISCELLANEOUS contract line on piers and walls: the lump sum a section '
     'starts at, quantity 0 until typed on the line. Was a literal 1000 in the '
     'code until sql/065.')
ON CONFLICT (key) DO NOTHING;

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('mono_slab', 'haul_off_cy', 12.50,
     'HAUL OFF on the slab sheet, $/CY of dirt, quantity 0 until typed. Was a '
     'literal 12.50 in the code until sql/065; piers and columns read this key '
     'at their own rates'),
    ('mono_slab', 'engineering_sf', 0.20,
     'ENGINEERING on the slab sheet, $/SF, off by default. Was a literal 0.20 '
     'in the code until sql/065; piers read this key at 1.05')
ON CONFLICT (kind, key) DO NOTHING;
