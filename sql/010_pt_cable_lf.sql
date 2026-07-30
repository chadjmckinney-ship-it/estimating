-- PT cable linear feet: slab spacing + cables per grade beam
-- Slab LF (one-way): SF / (spacing_in / 12)  =  SF × 12 / spacing_in
-- GB LF: pt_cables_count × length_lf
-- Apply: psql -d estimating -f sql/010_pt_cable_lf.sql

BEGIN;

ALTER TABLE mono_slabs
    ADD COLUMN IF NOT EXISTS pt_spacing_in numeric(8, 3)
        CHECK (pt_spacing_in IS NULL OR pt_spacing_in > 0),
    ADD COLUMN IF NOT EXISTS calc_pt_slab_lf numeric(14, 3),
    ADD COLUMN IF NOT EXISTS calc_pt_gb_lf numeric(14, 3),
    ADD COLUMN IF NOT EXISTS calc_pt_cable_lf numeric(14, 3);

COMMENT ON COLUMN mono_slabs.pt_spacing_in IS
    'SOG PT cable spacing (inches o.c.). Slab cable LF = SF × 12 / spacing_in when PT';
COMMENT ON COLUMN mono_slabs.calc_pt_slab_lf IS 'Slab PT cable LF from spacing';
COMMENT ON COLUMN mono_slabs.calc_pt_gb_lf IS 'Sum of grade beam PT cable LF';
COMMENT ON COLUMN mono_slabs.calc_pt_cable_lf IS 'Total PT cable LF = slab + grade beams';

ALTER TABLE grade_beams
    ADD COLUMN IF NOT EXISTS pt_cables_count integer
        CHECK (pt_cables_count IS NULL OR pt_cables_count >= 0),
    ADD COLUMN IF NOT EXISTS calc_pt_cable_lf numeric(14, 3);

COMMENT ON COLUMN grade_beams.pt_cables_count IS
    'Number of PT cables in this grade beam type; LF = count × length_lf';
COMMENT ON COLUMN grade_beams.calc_pt_cable_lf IS 'PT cable LF for this GB type';

COMMIT;
