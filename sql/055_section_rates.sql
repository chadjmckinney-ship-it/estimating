-- 055_section_rates.sql
--
-- Rates that belong to ONE SECTION, and rules that belong to one JOB.
--
-- Chad, 2026-09-04, asked for the settings to be editable per estimate:
--
--   "lets say a place and finish sub says for a project, he can do it for
--    less because of the size of the pours.."
--
-- and then, asked where the override should live: **"I think making rates
-- changes per section is what I would like the best"**, with the per-estimate
-- layer kept underneath it.
--
-- ---------------------------------------------------------------------------
-- What already existed, and what did not
-- ---------------------------------------------------------------------------
--
-- Half of the ask was already built and had not been found. A PRICE is on the
-- estimate's price sheet (sql/048-049), scoped by assembly, and the Prices
-- screen has been editing it per job since then — "Paving — where it differs
-- from the company rate", with Place & finish labor a row in it.
--
-- Two things were genuinely missing:
--
--   1. **The sheet is per ESTIMATE.** A job with two paving sections could not
--      say "the sub is cheaper on the big pours and not on the little ones" —
--      editing the paving rate moved both. That is the sentence Chad actually
--      wrote: the size of the pours is a property of the SECTION.
--
--   2. **RULES had no per-job override at all.** Waste, form %, supervision
--      pacing and every divisor are read live from `assembly_rates` and
--      `system_settings`. Three of them (waste_concrete, waste_sand,
--      waste_rebar) and form_percent are columns on `estimate_sections`; the
--      other twenty-odd had nowhere to be said differently.
--
-- ---------------------------------------------------------------------------
-- The ladder, after this
-- ---------------------------------------------------------------------------
--
--     section_rates          this section, whatever it is        <- NEW
--       estimate price sheet    this job's PRICES, frozen at its pull
--       estimate_rules          this job's RULES, read live      <- NEW
--         assembly_rates        what this ASSEMBLY does
--           system_settings     what the COMPANY does
--             code default      the last resort
--
-- One table wins outright and one sits in the middle, because they answer
-- different questions. `section_rates` is "on this bit of work, the number is
-- X" and it beats everything, price or rule. `estimate_rules` is "on this job
-- we are wasting 8% concrete", which is a job fact, so it sits where the price
-- sheet sits — and it is deliberately NOT on the sheet, because the sheet
-- FREEZES what it holds and a rule must stay live (see
-- docs/specs/estimate-price-sheet-spec.md, "What is a price, and what is a rule").
-- An unoverridden rule still reaches every old job on recalc, which is the
-- whole reason rules are not frozen.
--
-- ---------------------------------------------------------------------------
-- Why a table and not more columns
-- ---------------------------------------------------------------------------
--
-- `estimate_sections` already carries four of these as columns —
-- waste_concrete, waste_sand, waste_rebar, form_percent — and adding the other
-- ninety would be ninety columns, ninety schema fields and ninety places to
-- forget one. The four that exist keep working and keep winning; they are
-- checked before this table, so no stored number moves.
--
-- ---------------------------------------------------------------------------
-- No prices in migrations (sql/044)
-- ---------------------------------------------------------------------------
--
-- Both tables ship EMPTY. An override is something somebody decided about one
-- job; there is no company default for it and there never will be. Empty means
-- every existing estimate resolves exactly as it did before this file ran,
-- which is the proof the change moved nothing.

-- ---------------------------------------------------------------------------
-- Per-section overrides — prices AND rules
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS section_rates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id  uuid NOT NULL REFERENCES estimate_sections(id) ON DELETE CASCADE,

    -- A key from price_book.MONETARY_KEYS or RULE_KEYS. Validated by the API
    -- rather than by a FK, because the registry lives in Python next to the
    -- code that reads it — a second copy in a table is a copy that drifts.
    key         text NOT NULL,
    value       numeric(14, 4) NOT NULL,

    -- Why. A rate that differs from the company's without a reason beside it
    -- is a number nobody can defend three months later, which is the same
    -- lesson the quote cards learned.
    note        text,

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT section_rates_section_key_key UNIQUE (section_id, key)
);

CREATE INDEX IF NOT EXISTS section_rates_section_idx ON section_rates (section_id);

COMMENT ON TABLE section_rates IS
    'Rates set on ONE section, price or rule (sql/055). Beats the estimate '
    'price sheet, estimate_rules, assembly_rates and system_settings. Chad, '
    '2026-09-04: "I think making rates changes per section is what I would '
    'like the best" - because the thing that makes a sub cheaper is the size '
    'of THESE pours, not the job.';

COMMENT ON COLUMN section_rates.value IS
    'The number this section uses. There is no "unset" row: an override that '
    'means nothing is DELETED, so the ladder below it takes over again. A row '
    'here always means somebody decided.';


-- ---------------------------------------------------------------------------
-- Per-estimate RULE overrides
-- ---------------------------------------------------------------------------
--
-- Prices do not need this: they are already on the sheet. Rules do, and they
-- cannot go on the sheet, because the sheet freezes and a rule must not.

CREATE TABLE IF NOT EXISTS estimate_rules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id uuid NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,

    key         text NOT NULL,
    value       numeric(14, 4) NOT NULL,
    note        text,

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT estimate_rules_estimate_key_key UNIQUE (estimate_id, key)
);

CREATE INDEX IF NOT EXISTS estimate_rules_estimate_idx ON estimate_rules (estimate_id);

COMMENT ON TABLE estimate_rules IS
    'RULE overrides for one job (sql/055) - waste, form %, pacing, divisors. '
    'Deliberately NOT on the price sheet: the sheet freezes what it holds, and '
    'a rule that froze would stop a correction reaching the jobs it was made '
    'for. A key with no row here reads live from the assembly and the company, '
    'exactly as before.';
