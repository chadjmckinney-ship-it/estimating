-- 046 — quote vs catalog comparison thresholds
--
-- Every quote now shows what the catalog would have charged for the same
-- package, and warns when the two are far apart. Drilling has had this since
-- piers were built (`rate_table_drill_cost`); rebar and PT had nothing.
--
-- WHY: on 2026-09-01 a rebar quote entered as `$0.65 LS` — sixty-five cents,
-- lump, against 21,945 lb of steel — understated the mono slab by $14,252.58
-- and sat behind a green "current" badge. The catalog said $14,263 for that
-- same steel. Nothing in the app put those two numbers next to each other.
--
-- The band is DELIBERATELY LOOSE (Chad, 2026-09-02). It is sized to catch
-- decimal-point and unit mistakes — a lump typed as a rate, $/ton entered as
-- $/lb — and to stay quiet on a real quote. A sub's genuine price is sometimes
-- a third of catalog; a badge that fires on every good buy is a badge people
-- learn to ignore, and an ignored badge is worse than none because it looks
-- like cover.
--
-- These are RATIOS, not prices — a rule about how far apart two numbers may be,
-- which is exactly what `system_settings` is for. See
-- claude/design-decisions.md, "A price comes from the catalog."
--
-- Override per assembly by adding an `assembly_rates` row with the same key.

INSERT INTO system_settings (key, value)
VALUES
  ('quote_warn_low_ratio',  to_jsonb('0.25'::text)),
  ('quote_warn_high_ratio', to_jsonb('4'::text))
ON CONFLICT (key) DO NOTHING;
