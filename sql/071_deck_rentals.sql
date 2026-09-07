-- 071_deck_rentals.sql
--
-- The elevated deck's rentals — forms, shoring, reshoring — as their own
-- card, with their own prices and a quote of their own.
--
-- Chad, 2026-09-07: "think we need to rework CIP elevated... giving it a
-- separate section from materials for form rentals, shoring and reshoring"
-- — "we usually rent forming materials and shoring for a project.. so
-- allowing a quote works" — "$0.5 forms, $0.75 shoring and reshoring".
--
-- Until now the deck's forming card carried FORM RENTAL SHORING (SF x $1.25
-- x 1.10, the sheet's F84) and RESHORING (SF x a blank rate x 1.10, F83)
-- among the lumber. Now three lines in a rentals group on the same line set:
--
--     FORM RENTAL         SF x $0.50 x forms_multiplier      (1.10)
--     SHORING RENTAL      SF x $0.75 x shoring_multiplier    (1.10)
--     RESHORING MATERIAL  SF x $0.75 x reshoring_multiplier  (1.10)
--
-- and a "shoring" quote (LS or $/SF) on a deck section replaces all three.
--
-- form_rental_shoring_sf retires: its $1.25 was forms and shoring together,
-- and Chad's split is $0.50 + $0.75. form_rental_shoring_multiplier — the
-- sheet's J83 "silently reused" (sql/052) — becomes shoring_multiplier
-- wherever anyone set it, and forms_multiplier joins it at the same 1.10.
-- reshoring_material_sf, "deliberately absent" since sql/052 because F83 is
-- blank, gets Chad's $0.75: the line prices from today, and the LBJ deck
-- moves up by that much (tests/deck_fixture.py names it).
--
-- Price sheets: the retired key comes off every sheet; the three live keys
-- go on at the assembly value, unedited, so no job reads them as unpriced
-- until its next pull.

-- The rates.
DELETE FROM assembly_rates WHERE key = 'form_rental_shoring_sf';
INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('cip_deck', 'form_rental_sf',        0.50, 'Chad, 2026-09-07: "$0.5 forms" -- half of the sheet''s F84 $1.25'),
    ('cip_deck', 'shoring_rental_sf',     0.75, 'Chad, 2026-09-07: "$0.75 shoring" -- the other half of F84'),
    ('cip_deck', 'reshoring_material_sf', 0.75, 'Chad, 2026-09-07: "$0.75 ... reshoring" -- F83 was blank; unpriced until today')
ON CONFLICT (kind, key) DO UPDATE SET value = excluded.value, note = excluded.note;

-- The allowances: one rule per line. The old name goes wherever it was set.
UPDATE assembly_rates   SET key = 'shoring_multiplier', note = '08 J83 -- shoring''s own rule since sql/071'
 WHERE key = 'form_rental_shoring_multiplier';
UPDATE estimate_rules   SET key = 'shoring_multiplier' WHERE key = 'form_rental_shoring_multiplier';
UPDATE section_rates    SET key = 'shoring_multiplier' WHERE key = 'form_rental_shoring_multiplier';
UPDATE system_settings  SET key = 'shoring_multiplier' WHERE key = 'form_rental_shoring_multiplier';
INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('cip_deck', 'forms_multiplier', 1.10, 'the same 1.10 as shoring and reshoring, as its own rule (sql/071)')
ON CONFLICT (kind, key) DO NOTHING;

-- The price sheets.
DELETE FROM estimate_prices WHERE ref_key = 'form_rental_shoring_sf';
DELETE FROM section_rates   WHERE key = 'form_rental_shoring_sf';
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', a.kind, a.key, k.label, k.unit, a.kind || ' rates', a.value, a.value
  FROM estimates e
 CROSS JOIN assembly_rates a
  JOIN (VALUES
          ('form_rental_sf',        'Form rental (deck)',    'SF'),
          ('shoring_rental_sf',     'Shoring rental (deck)', 'SF'),
          ('reshoring_material_sf', 'Reshoring material',    'SF')
       ) AS k(key, label, unit) ON k.key = a.key
 WHERE a.kind = 'cip_deck'
ON CONFLICT DO NOTHING;

-- The quote kind. sql/039's CHECK named the three kinds it had; a fourth joins.
ALTER TABLE section_quotes DROP CONSTRAINT IF EXISTS section_quotes_kind_ck;
ALTER TABLE section_quotes
    ADD CONSTRAINT section_quotes_kind_ck
    CHECK (kind IN ('drilling', 'rebar', 'pt', 'shoring'));
