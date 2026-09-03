-- 041_walls_drop_pilasters.sql
--
-- Take the pilaster fields back out of wall_runs.
--
-- sql/040 carried them because the workbook's 06 sheet has the columns, marked
-- UNTESTED because no LBJ row fills them. Chad's answer to why:
--
--   "I dont use the pilaster section because it doesnt let me add enough info
--    and I just use column sheet for it since it is basically a short column."
--
-- So they are not merely untested, they are never used -- three input columns
-- and two calc columns that would sit there forever looking like a feature.
-- That is the exact liability sql/038 was written about: an unread column with
-- a comment promising behaviour. A pilaster is a short column and belongs in
-- the columns assembly, where it can carry a full schedule.
--
-- Written as a separate migration rather than an edit to sql/040 so it is safe
-- whether or not 040 has already been applied.
--
-- ---------------------------------------------------------------------------
-- What survives, and why
-- ---------------------------------------------------------------------------
--
-- The sheet's steel formula ends with:
--
--     ((T*U*S*0.03*0.2836*G)/12 + 4) * (G/H) * bar_lb
--
-- T/U/S are the pilaster dimensions and count. With no pilasters the whole
-- product collapses and the bare **+ 4** survives, so every row with horizontal
-- steel picks up 4 ft of bar per horizontal course -- 12.5 lb on LBJ's biggest
-- row, ~200 lb across the job, and part of the reconciled number.
--
-- Dropping pilasters does NOT drop that. It is renamed to what it appears to
-- be: a lap allowance on horizontal steel, 4 ft per course, stated as a rate
-- so it can be changed rather than hidden inside a formula.

ALTER TABLE wall_runs DROP COLUMN IF EXISTS pilaster_qty;
ALTER TABLE wall_runs DROP COLUMN IF EXISTS pilaster_length_in;
ALTER TABLE wall_runs DROP COLUMN IF EXISTS pilaster_width_in;
ALTER TABLE wall_runs DROP COLUMN IF EXISTS calc_pilaster_concrete_cy;

ALTER TABLE wall_runs
    RENAME COLUMN calc_pilaster_rebar_lb TO calc_lap_rebar_lb;

COMMENT ON COLUMN wall_runs.calc_lap_rebar_lb IS
    'Lap allowance on horizontal steel: horiz_lap_ft_per_course ft of bar per '
    'course, from the bare "+ 4" the workbook leaves in its pilaster term. '
    'Part of the reconciled 33,727.83 lb -- do not remove it without moving '
    'the golden number too.';

INSERT INTO assembly_rates (kind, key, value, note) VALUES
    ('walls_footings', 'horiz_lap_ft_per_course', 4.00,
     '06 V-column - the bare "+4" left in the pilaster term; laps on horizontal steel')
ON CONFLICT (kind, key) DO NOTHING;
