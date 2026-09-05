-- 057_estimate_sections_bounds.sql
--
-- The bounds that did not follow the columns to sections.
--
-- sql/017, 020 and 026 put CHECK constraints on estimates.form_percent,
-- estimates.waste_concrete / waste_sand / waste_rebar, estimates.margin_pct
-- and estimates.contingency_pct — the August "silently stale" fixes, the
-- reasoning in sql/020's own header: a waste factor of 5 is 500%, and a
-- number like that is far more likely a slipped decimal than a decision.
--
-- sql/033 created estimate_sections with all seven of those columns and no
-- CHECK on any of them; sql/034 moved ownership to the section and dropped
-- the checked originals from estimates. The invariant was lost in the move.
-- Found by the 2026-09-04 full check (docs: Estimating App Audit 2026-09-04).
--
-- The API bounds these (schemas/estimate_section.py: 0–1 on the wastes, 0–2 on
-- markup and form %), so the screen was never the way in. psql, a script, a
-- job rule and backend/debug_section.py are. The database is where the
-- invariant belongs, because it is the one place every writer passes through.
--
-- Same ranges as the originals. Margin and contingency are NOT NULL and so
-- must be in range; form % and the wastes may be NULL (inherit the ladder) or
-- in range. Every live row on 2026-09-04 satisfied these before they were
-- added; ADD CONSTRAINT validates existing rows, so a database that does not
-- refuses this file rather than half-applying it — check with:
--
--   SELECT id, name, margin_pct, contingency_pct, form_percent,
--          waste_concrete, waste_sand, waste_rebar
--     FROM estimate_sections
--    WHERE margin_pct NOT BETWEEN 0 AND 2
--       OR contingency_pct NOT BETWEEN 0 AND 2
--       OR form_percent NOT BETWEEN 0 AND 2
--       OR waste_concrete NOT BETWEEN 0 AND 1
--       OR waste_sand NOT BETWEEN 0 AND 1
--       OR waste_rebar NOT BETWEEN 0 AND 1;

ALTER TABLE estimate_sections
    DROP CONSTRAINT IF EXISTS estimate_sections_margin_pct_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_margin_pct_check
    CHECK (margin_pct >= 0 AND margin_pct <= 2);

ALTER TABLE estimate_sections
    DROP CONSTRAINT IF EXISTS estimate_sections_contingency_pct_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_contingency_pct_check
    CHECK (contingency_pct >= 0 AND contingency_pct <= 2);

ALTER TABLE estimate_sections
    DROP CONSTRAINT IF EXISTS estimate_sections_form_percent_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_form_percent_check
    CHECK (form_percent IS NULL OR (form_percent >= 0 AND form_percent <= 2));

ALTER TABLE estimate_sections
    DROP CONSTRAINT IF EXISTS estimate_sections_waste_concrete_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_waste_concrete_check
    CHECK (waste_concrete IS NULL OR (waste_concrete >= 0 AND waste_concrete <= 1));

ALTER TABLE estimate_sections
    DROP CONSTRAINT IF EXISTS estimate_sections_waste_sand_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_waste_sand_check
    CHECK (waste_sand IS NULL OR (waste_sand >= 0 AND waste_sand <= 1));

ALTER TABLE estimate_sections
    DROP CONSTRAINT IF EXISTS estimate_sections_waste_rebar_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_waste_rebar_check
    CHECK (waste_rebar IS NULL OR (waste_rebar >= 0 AND waste_rebar <= 1));

COMMENT ON COLUMN estimate_sections.margin_pct IS
    'Markup on cost as a decimal, 0–2 (0.18 = 18%). Sale = cost x (1 + margin + contingency).';
COMMENT ON COLUMN estimate_sections.contingency_pct IS
    'Contingency on cost as a decimal, 0–2. Added to margin, not compounded.';
COMMENT ON COLUMN estimate_sections.form_percent IS
    'Excel "% of forming" for this section, 0–2. NULL = the rules ladder (section_rates, '
    'estimate_rules, assembly_rates, system_settings.form_percent).';
COMMENT ON COLUMN estimate_sections.waste_concrete IS
    'Concrete waste factor 0–1 (0.06 = 6%). NULL = the rules ladder.';
COMMENT ON COLUMN estimate_sections.waste_sand IS
    'Sand waste factor 0–1. NULL = the rules ladder.';
COMMENT ON COLUMN estimate_sections.waste_rebar IS
    'Rebar waste factor 0–1. NULL = the rules ladder. On a slab this is the LAP allowance; '
    'on piers it is genuine waste — same column, meaning decided by the assembly.';
