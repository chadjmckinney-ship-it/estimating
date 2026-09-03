-- 039_section_quotes.sql
--
-- One quote mechanism, not a column set per material.
--
-- sql/037 + sql/038 put the drilling quote on estimate_sections as three
-- columns. Adding PT and rebar the same way would mean nine columns, three
-- copies of the stamping logic and three copies of the staleness check -- and
-- the note in models/estimate_section.py already says what happens then:
-- private copies of the same idea are how they stop agreeing.
--
-- So quotes become rows. A section can carry at most one quote of each kind,
-- and the drilling quote migrates in with its baseline intact.
--
-- ---------------------------------------------------------------------------
-- The distinction that runs through the whole design: LUMP vs UNIT-PRICED
-- ---------------------------------------------------------------------------
--
-- A lump sum ("$54,500 for the drilling") is priced against a takeoff that can
-- move underneath it. It needs its baseline stamped and it can go stale.
--
-- A unit price ("$1,240/ton delivered") cannot go stale. It follows the
-- takeoff by construction -- more tons, more money, automatically. There is
-- nothing to warn about, and warning anyway would train people to ignore the
-- banner that matters.
--
-- baseline_qty is therefore populated for LS quotes and left NULL for
-- unit-priced ones, and the staleness check ignores anything that is not a
-- lump.

CREATE TABLE IF NOT EXISTS section_quotes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections(id) ON DELETE CASCADE,

    -- What the quote prices. 'drilling' | 'rebar' | 'pt'.
    kind        text NOT NULL,

    -- The number on the paper, and what it is per.
    --   LS  a lump for the package
    --   TON $/ton      CWT $/cwt      LB  $/lb      SF  $/SF
    amount      numeric(14, 4) NOT NULL CHECK (amount >= 0),
    unit        text NOT NULL DEFAULT 'LS',

    -- The takeoff quantity this was priced against, stamped on write and never
    -- on recalc. LS only -- see the note above.
    baseline_qty  numeric(14, 3),
    baseline_unit text,

    -- Who quoted it and what it covers. The exclusions are the part that costs
    -- money later and they do not fit a column.
    note        text,

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT section_quotes_kind_ck
        CHECK (kind IN ('drilling', 'rebar', 'pt')),
    CONSTRAINT section_quotes_unit_ck
        CHECK (unit IN ('LS', 'TON', 'CWT', 'LB', 'SF'))
);

-- One quote of each kind per section. A second rebar quote is a replacement,
-- not an addition -- two would silently both apply.
CREATE UNIQUE INDEX IF NOT EXISTS section_quotes_section_kind_uq
    ON section_quotes (section_id, kind);

COMMENT ON TABLE section_quotes IS
    'Real quotes that replace a computed cost on a section. A lump is spread '
    'across the section''s rows by the driver the quote priced; a unit price '
    'replaces the catalog rate. Material only -- a quote never displaces a '
    'labor line, so TIE STEEL still bills against a rebar quote.';

COMMENT ON COLUMN section_quotes.baseline_qty IS
    'Takeoff quantity when the quote was written -- drilled LF for drilling, '
    'rebar lb for rebar, PT SF for pt. Populated for LS only. Recalc must '
    'never update it: if the baseline chased the takeoff, the staleness check '
    'could never fire.';

-- --------------------------------------------- migrate the drilling quote ---
-- Carries the stamped LF across, so a quote entered before this migration
-- keeps its staleness baseline rather than silently reading as unverifiable.

INSERT INTO section_quotes (section_id, kind, amount, unit, baseline_qty, baseline_unit, note)
SELECT id, 'drilling', pier_drill_quote, 'LS', pier_drill_quote_lf, 'LF', pier_drill_quote_note
FROM estimate_sections
WHERE pier_drill_quote IS NOT NULL AND pier_drill_quote > 0
ON CONFLICT (section_id, kind) DO NOTHING;

-- The columns go rather than lingering unread. An unread column with a comment
-- promising behaviour is exactly the bug sql/038 was written to fix; leaving
-- these behind would recreate it one migration later.
ALTER TABLE estimate_sections DROP COLUMN IF EXISTS pier_drill_quote;
ALTER TABLE estimate_sections DROP COLUMN IF EXISTS pier_drill_quote_lf;
ALTER TABLE estimate_sections DROP COLUMN IF EXISTS pier_drill_quote_note;
