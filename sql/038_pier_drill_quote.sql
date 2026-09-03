-- 038_pier_drill_quote.sql
--
-- Make the drilling quote real.
--
-- sql/037 added estimate_sections.pier_drill_quote and a comment promising it
-- REPLACES the pier_drill_rates computation. Nothing ever read the column: not
-- the model, not the schema, not costing, not the UI. A number typed there
-- changed nothing and said nothing. This migration is the other half.
--
-- Drilling is the largest single line on a pier job -- $58,032 of LBJ's
-- $211,441 direct cost, 27% -- and in the field it is a hard number from the
-- drilling sub, not an estimate. The rate table is what you use until the
-- quote arrives, not the other way round.
--
-- Two columns, both about the same danger: a quote is priced against a
-- takeoff, and takeoffs move. Stamping the LF the quote was given for is what
-- lets the screen say "this was quoted against 2,348 LF and you now have
-- 2,612" instead of quietly carrying a stale lump sum to the bid.

ALTER TABLE estimate_sections
    ADD COLUMN IF NOT EXISTS pier_drill_quote_lf numeric(12, 3);

COMMENT ON COLUMN estimate_sections.pier_drill_quote_lf IS
    'Total drilled LF in this section at the moment pier_drill_quote was '
    'entered. Stamped on write, never on recalc -- it is the baseline the '
    'staleness check compares against, so recalc must not move it.';

ALTER TABLE estimate_sections
    ADD COLUMN IF NOT EXISTS pier_drill_quote_note text;

COMMENT ON COLUMN estimate_sections.pier_drill_quote_note IS
    'Who quoted it and what it covers -- casing, rock, mobilization. Free '
    'text on purpose: the exclusions on a drilling quote are the part that '
    'costs money later, and they do not fit a column.';

-- A quote is a section-level lump, so it only means anything on a piers
-- section. Nothing enforces that in the schema (kind is mutable and the
-- column is nullable); piers.py ignores it for any other kind.
