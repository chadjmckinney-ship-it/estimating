-- Poly / Stego (vapor barrier) SF for mono pours
-- Excel 04-PT SOG: beam poly area = (2 × H_in / 12) × L_ft  (two sides only;
-- pour SF already covers the horizontal plane / beam bottoms)
-- Apply: psql -d estimating -f sql/014_poly_stego_sf.sql

BEGIN;

-- Excel AS = HEIGHT_IN * 2 / 12 (SF per LF); × length → SF
-- width_in kept for API/signature compatibility; not used in poly (bottom in pour SF)
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

ALTER TABLE grade_beams
    ADD COLUMN IF NOT EXISTS calc_poly_sf numeric(14, 3);

COMMENT ON COLUMN grade_beams.calc_poly_sf IS
    '(2 * height_in / 12) * length_lf — Excel poly area; bottom in pour SF';

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS calc_poly_slab_sf numeric(14, 3),
    ADD COLUMN IF NOT EXISTS calc_poly_gb_sf numeric(14, 3),
    ADD COLUMN IF NOT EXISTS calc_poly_sf numeric(14, 3);

COMMENT ON COLUMN mono_slabs.calc_poly_slab_sf IS 'Pour square_footage (slab plane)';
COMMENT ON COLUMN mono_slabs.calc_poly_gb_sf IS
    'Sum of beam wrap poly SF (GB + Exp + Drop)';
COMMENT ON COLUMN mono_slabs.calc_poly_sf IS
    '(slab + beams) × (1 + waste_poly); total vapor barrier SF';

INSERT INTO system_settings (key, value, description)
VALUES (
    'waste_poly',
    '0.10'::jsonb,
    'Poly/Stego waste factor (decimal). Total SF = (slab + beam wrap) × (1 + waste).'
)
ON CONFLICT (key) DO NOTHING;

-- Backfill beam wrap SF
UPDATE grade_beams
SET calc_poly_sf = calc_poly_beam_sf(width_in, height_in, length_lf)
WHERE calc_poly_sf IS NULL;

-- Backfill pour totals (no waste on partial if waste_poly missing — use 0.10)
UPDATE mono_slabs ms
SET
    calc_poly_slab_sf = ms.square_footage,
    calc_poly_gb_sf = coalesce((
        SELECT sum(calc_poly_beam_sf(gb.width_in, gb.height_in, gb.length_lf))
        FROM grade_beams gb
        WHERE gb.mono_slab_id = ms.id
    ), 0),
    calc_poly_sf = round(
        (
            ms.square_footage
            + coalesce((
                SELECT sum(calc_poly_beam_sf(gb.width_in, gb.height_in, gb.length_lf))
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
