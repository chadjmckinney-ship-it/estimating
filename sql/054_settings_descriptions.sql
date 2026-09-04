-- 054_settings_descriptions.sql
--
-- Documentation only. No value moves, no schema changes.
--
-- sql/053 gave the company settings a screen's worth of metadata to serve —
-- price or rule, label, unit, group, what a change rewrites — and building
-- that screen made one thing obvious: the DESCRIPTION is the only part of a
-- setting that says what it is for, and two keys have none.
--
-- A setting with no description is a number on a screen with no way to know
-- whether touching it is safe. Both of these are, and both are easy to
-- misread as money.

UPDATE system_settings SET description =
    'How far BELOW the catalog a quote may sit before the card warns — 0.25 '
    'means a quarter of what our own prices come to. Deliberately loose: it '
    'fires on decimal-point and unit mistakes (a lump typed as a rate, $/ton '
    'entered as $/lb) and stays quiet on a real buy. A badge that fires on '
    'every good quote is one people learn to ignore, and an ignored badge is '
    'worse than none because it looks like cover. A RATIO, not a price.'
WHERE key = 'quote_warn_low_ratio';

UPDATE system_settings SET description =
    'How far ABOVE the catalog a quote may sit before the card warns — 4 '
    'means four times what our own prices come to. See quote_warn_low_ratio '
    'for why the band is wide. A RATIO, not a price.'
WHERE key = 'quote_warn_high_ratio';

-- And one that describes itself as a slab rate when every assembly reads it.
UPDATE system_settings SET description =
    'Tie steel labor $/TON. The COMPANY figure — every assembly reads it, and '
    'an assembly with its own number overrides it in assembly_rates (sql/035). '
    'Piers, walls, columns and decks all bill every pound; the slab carves out '
    'a free band first (labor_tie_steel_free_lb_per_sf).'
WHERE key = 'labor_tie_steel_ton';
