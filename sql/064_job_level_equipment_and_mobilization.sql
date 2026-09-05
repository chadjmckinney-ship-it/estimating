-- 064_job_level_equipment_and_mobilization.sql
--
-- Mobilization and the equipment day rates are the job's, not the section's.
--
-- Chad, 2026-09-05, right after "Rates are always per section" seeded every
-- section-level price onto every section: "mobilization and the equipment
-- day rates are per job." So those keys moved to price_book.ESTIMATE_LEVEL_KEYS
-- -- set on the job's price sheet, shown read-only on the section card -- and
-- the rows the seeding wrote for them come back out, or the ladder's top rung
-- would keep serving a section-level value for a key nobody can set there.
--
-- Nothing moves: every one of these rows was written at the value the section
-- already resolved to (the job sheet's, or the code default), so removing it
-- hands the section back exactly that number. On the live database on
-- 2026-09-05 this is 25 rows -- mobilization_ls x7, equip_misc_day_rate x7,
-- equip_vault_day_rate x7, equip_storage_day_rate x2, equip_fork_truck_day_rate
-- x1, equip_easy_drill_day_rate x1 -- all noted "seeded 2026-09-05 (backfill)".

DELETE FROM section_rates
 WHERE key = 'mobilization_ls'
    OR key ~ '^equip_.*_day_rate$';
