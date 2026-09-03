-- 048 — the estimate price sheet (stage 1: mixes and materials)
--
-- claude/estimate-price-sheet-spec.md. Chad, 2026-09-02: "I like having a
-- master list of rough mix prices that we get from suppliers that we update
-- as we get them, then as we start an estimate, it pulls those numbers and we
-- can update when a supplier gives us a quote."
--
-- One estimate, one sheet. Every price the job uses is on it by name, with
-- what the master list said when it was pulled and what this job actually
-- pays. An estimate reads its own sheet, so the catalog can move without
-- moving a bid — the −$4,984.91 morning of 2026-08-31 becomes a list of what
-- changed instead.
--
-- Stage 1 covers mixes and materials (~59% of a slab section). Equipment,
-- settings, assembly rates and drill rates follow in stages 2–4; the `kind`
-- check already admits them so those stages add rows, not columns.

CREATE TABLE estimate_prices (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,

    -- What kind of price this is, which decides how it is looked up.
    kind            text NOT NULL CHECK (kind IN
                      ('mix', 'material', 'equipment', 'setting', 'assembly_rate', 'drill_rate')),
    scope           text,           -- assembly kind for assembly_rate rows; NULL = global
    ref_id          integer,        -- mix_designs / materials / equipment id
    ref_key         text,           -- settings key, rate key, drill diameter

    -- Captured at pull, so the screen reads without joining anything and a
    -- catalog rename does not rewrite history.
    label           text NOT NULL,
    unit            text,
    category        text,           -- for grouping on screen

    catalog_value   numeric(14, 4), -- what the master list said WHEN PULLED
    value           numeric(14, 4) NOT NULL,  -- what this job uses
    is_edited       boolean NOT NULL DEFAULT false,
    note            text,

    pulled_at       timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- One row per price per estimate. The key is polymorphic — an id for catalog
-- items, a key for settings and rates — so the uniqueness is on whichever
-- half is present.
CREATE UNIQUE INDEX estimate_prices_uidx ON estimate_prices
    (estimate_id, kind, coalesce(scope, ''), coalesce(ref_key, ref_id::text));

CREATE INDEX estimate_prices_estimate_id_idx ON estimate_prices (estimate_id);

COMMENT ON TABLE estimate_prices IS
    'The prices one estimate was built with. Pulled from the master list '
    '(mix_designs / materials / ...), editable per job, never moved by a '
    'catalog change. catalog_value is the master price at pull time; value is '
    'what this job pays; is_edited says a person changed it (sql/048).';

COMMENT ON COLUMN estimate_prices.value IS
    'What this job pays. NOT NULL: a pull never writes a zero from an unpriced '
    'master item — it reports the item and leaves the row absent, so the '
    'section shows it as unpriced (sql/047) rather than free.';

-- ---------------------------------------------------------------------------
-- Backfill: every existing estimate gets a sheet from the master list AS IT
-- STANDS. This moves no number — the book falls back to the catalog for a
-- missing row and the backfilled rows carry the catalog's own values, so a
-- recalc after this migration produces the totals it produced before it.
-- That is asserted against LBJ 152b3611 in tests/test_price_sheet.py and was
-- verified live on 2026-09-02.
--
-- Unpriced master items (NULL unit_cost) are skipped, per decision 5.
-- ---------------------------------------------------------------------------
INSERT INTO estimate_prices
    (estimate_id, kind, ref_id, label, unit, category, catalog_value, value)
SELECT e.id, 'mix', m.id, m.code, m.unit, 'concrete', m.unit_cost, m.unit_cost
  FROM estimates e
 CROSS JOIN mix_designs m
 WHERE m.is_active AND m.unit_cost IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO estimate_prices
    (estimate_id, kind, ref_id, label, unit, category, catalog_value, value)
SELECT e.id, 'material', mt.id, mt.name, mt.unit, mt.category, mt.unit_cost, mt.unit_cost
  FROM estimates e
 CROSS JOIN materials mt
 WHERE coalesce(mt.is_active, true) AND mt.unit_cost IS NOT NULL
ON CONFLICT DO NOTHING;
