-- Align beam poly with Excel 04-PT SOG:
--   poly area per LF = (2 × HEIGHT_IN) / 12
--   beam_poly_sf     = (2 × height_in / 12) × length_lf
-- Pour SF already covers beam bottoms; do not add width.
-- Apply: psql -d estimating -f sql/015_poly_sides_only.sql

BEGIN;

CREATE OR REPLACE FUNCTION calc_poly_beam_sf(
    width_in numeric,
    height_in numeric,
    length_lf numeric
) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN height_in IS NULL OR length_lf IS NULL THEN NULL
        WHEN height_in <= 0 OR length_lf < 0 THEN 0
        ELSE round((2 * height_in / 12.0) * length_lf, 3)
    END;
$$;

COMMENT ON FUNCTION calc_poly_beam_sf IS
    'Poly SF for one beam (Excel): (2 × H″ / 12) × L ft — two vertical sides only';

COMMENT ON COLUMN grade_beams.calc_poly_sf IS
    '(2 * height_in / 12) * length_lf — Excel poly area; bottom in pour SF';

-- Recalculate all beam wrap SF
UPDATE grade_beams
SET calc_poly_sf = calc_poly_beam_sf(width_in, height_in, length_lf);

-- Recalculate pour totals (slab + beams) × (1 + waste_poly)
UPDATE mono_slabs ms
SET
    calc_poly_slab_sf = ms.square_footage,
    calc_poly_gb_sf = coalesce((
        SELECT sum(gb.calc_poly_sf)
        FROM grade_beams gb
        WHERE gb.mono_slab_id = ms.id
    ), 0),
    calc_poly_sf = round(
        (
            ms.square_footage
            + coalesce((
                SELECT sum(gb.calc_poly_sf)
                FROM grade_beams gb
                WHERE gb.mono_slab_id = ms.id
            ), 0)
        ) * (1 + coalesce(
            (SELECT (value #>> '{}')::numeric FROM system_settings WHERE key = 'waste_poly'),
            0.10
        )),
        3
    );

COMMIT;
