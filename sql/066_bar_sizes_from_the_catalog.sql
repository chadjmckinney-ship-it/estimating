-- 066_bar_sizes_from_the_catalog.sql
--
-- Every bar size comes from the catalog, and the catalog knows #14 and #18.
--
-- bar_weights (sql/001) held #3 through #11 and a CHECK saying so, and only
-- pier_groups and the grade-beam tables pointed at it. wall_runs and
-- column_types took a bare integer, deck_levels only asked for > 0, the
-- schemas allowed 0 to 20, and the grids took a number box. A #14 column
-- vertical — real on a heavy column — weighed NOTHING in every steel formula,
-- silently, because bar_lb_per_ft found no row (audit 2026-09-04, P3; batch 1
-- on Chad's "yes, start batch 1", 2026-09-06).
--
-- Now: #14 (7.65 lb/ft) and #18 (13.60 lb/ft, ASTM A615) join the catalog,
-- the 3-11 CHECK goes, and the seventeen bar-size columns that were bare
-- become foreign keys to it (pier_groups and grade_beams already were;
-- grade_beam_details is a view over grade_beams) — so a size the catalog
-- lacks cannot be stored, let alone weigh nothing. Live data on 2026-09-06
-- used #4 through #10 only; nothing is touched. Each step checks first, so
-- the file is safe to run twice.

ALTER TABLE bar_weights DROP CONSTRAINT IF EXISTS bar_weights_bar_size_check;

INSERT INTO bar_weights (bar_size, weight_lb_per_ft) VALUES
    (14, 7.6500),
    (18, 13.6000)
ON CONFLICT (bar_size) DO NOTHING;

DO $$
DECLARE
    r record;
    cname text;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('wall_runs', 'horiz_size'), ('wall_runs', 'vert_size'),
            ('wall_runs', 'ftg_bot_size'), ('wall_runs', 'ftg_top_size'),
            ('column_types', 'vert1_size'), ('column_types', 'vert2_size'), ('column_types', 'vert3_size'),
            ('column_types', 'tie_size'), ('column_types', 'dowel_size'),
            ('deck_levels', 'top_bar_size'), ('deck_levels', 'bot_bar_size'),
            ('estimate_beam_types', 'top_bars_size'), ('estimate_beam_types', 'bottom_bars_size'),
            ('estimate_beam_types', 'mid_bars_size'), ('estimate_beam_types', 'stirrup_size'),
            ('estimate_beam_types', 'l_bars_size'),
            ('mono_slabs', 'slab_bar_size')
        ) AS t(tbl, col)
    LOOP
        cname := r.tbl || '_' || r.col || '_bar_fkey';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = cname) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES bar_weights (bar_size)',
                r.tbl, cname, r.col
            );
        END IF;
    END LOOP;
END $$;

COMMENT ON TABLE bar_weights IS
    'ASTM A615 bar weights, #3-#11 and (sql/066) #14 and #18. Every bar-size '
    'column in the app is a foreign key here: a size not in this table cannot '
    'be stored, so nothing can weigh zero by accident.';
