-- 070_out_of_town_is_the_jobs.sql
--
-- The out-of-town day rate is the job's, not the section's.
--
-- Chad, 2026-09-07: "the out of town day rate it is per job." docs/specs/
-- section-rates.md had left it the one day rate still at section level —
-- "neither, and nobody has said" — when sql/064 moved mobilization and the
-- equipment day rates up to the job. Same treatment now: the key joins
-- price_book.ESTIMATE_LEVEL_KEYS (set on the job's price sheet, shown
-- read-only on the section card), and the rows the 2026-09-05 seeding wrote
-- for it come back out, or the ladder's top rung would keep serving a
-- section-level value for a key nobody can set there.
--
-- Nothing moves. On the live database on 2026-09-07 this is six rows, every
-- one noted "seeded 2026-09-05 (backfill)" and written at the value the
-- section already resolved to — 250 on piers and 200 on columns (their
-- assembly rates), 200 on paving and walls (the code default) — so removing
-- them hands each section back exactly that number.

DELETE FROM section_rates WHERE key = 'out_of_town_day_rate';
