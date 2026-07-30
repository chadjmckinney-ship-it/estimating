-- Grade beams become a per-estimate type library plus per-pour lengths.
--
-- Sections were re-keyed for every pour they appeared in: the LBJ import held
-- 80 beam rows describing only 9 distinct sections across 17 pours, and its
-- labels already read "Beam 1 (type 1)" .. "Drops (type 9)". The schedule now
-- lives once per estimate in estimate_beam_types; grade_beams keeps only which
-- type a pour uses and how much of it.
--
--   estimate_beam_types   label, kind, W, H, bars, stirrups, L-bars, PT cables
--   grade_beams           mono_slab_id, beam_type_id, length_lf
--
-- Existing rows are deduped on (kind, dimensions, full bar schedule) within an
-- estimate. Verified before writing this: no label maps to two sections, and no
-- pour lists the same section twice, so the mapping is 1:1 and lossless.
--
-- kind lives on the type — a section is a grade beam, an exposed GB or a drop by
-- what it is, and the UI already separates them. A section used in two roles
-- becomes two types.
--
-- View grade_beam_details presents the joined shape so the rollups and drivers
-- that filter on kind keep reading one relation.
--
-- Stored calcs must be rewritten after applying:
--   curl -s -X POST localhost:8001/api/system-settings/recalc-all
--
-- Apply: psql -d estimating -f sql/025_estimate_beam_types.sql

BEGIN;

-- ------------------------------------------------------------- type table ----

CREATE TABLE IF NOT EXISTS estimate_beam_types (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id        uuid NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    label              text NOT NULL,
    kind               text NOT NULL DEFAULT 'grade_beam'
                       CHECK (kind IN ('grade_beam', 'exposed', 'drop')),
    width_in           numeric(8, 3) NOT NULL CHECK (width_in > 0),
    height_in          numeric(8, 3) NOT NULL CHECK (height_in > 0),
    top_bars_count     integer  CHECK (top_bars_count IS NULL OR top_bars_count >= 0),
    top_bars_size      smallint CHECK (top_bars_size IS NULL OR top_bars_size BETWEEN 3 AND 11),
    bottom_bars_count  integer  CHECK (bottom_bars_count IS NULL OR bottom_bars_count >= 0),
    bottom_bars_size   smallint CHECK (bottom_bars_size IS NULL OR bottom_bars_size BETWEEN 3 AND 11),
    mid_bars_count     integer  CHECK (mid_bars_count IS NULL OR mid_bars_count >= 0),
    mid_bars_size      smallint CHECK (mid_bars_size IS NULL OR mid_bars_size BETWEEN 3 AND 11),
    stirrup_size       smallint CHECK (stirrup_size IS NULL OR stirrup_size BETWEEN 3 AND 11),
    stirrup_spacing_in numeric(8, 3) CHECK (stirrup_spacing_in IS NULL OR stirrup_spacing_in > 0),
    l_bars_count       integer  CHECK (l_bars_count IS NULL OR l_bars_count >= 0),
    l_bars_size        smallint CHECK (l_bars_size IS NULL OR l_bars_size BETWEEN 3 AND 11),
    l_bars_spacing_in  numeric(8, 3) CHECK (l_bars_spacing_in IS NULL OR l_bars_spacing_in > 0),
    pt_cables_count    integer  CHECK (pt_cables_count IS NULL OR pt_cables_count >= 0),
    notes              text,
    sort_order         integer NOT NULL DEFAULT 0,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS estimate_beam_types_label_idx
    ON estimate_beam_types (estimate_id, label);
CREATE INDEX IF NOT EXISTS estimate_beam_types_estimate_idx
    ON estimate_beam_types (estimate_id);

COMMENT ON TABLE estimate_beam_types IS
    'Per-estimate grade beam / exposed GB / drop schedule. Pours reference a type '
    'and supply only length — see grade_beams.';

-- --------------------------------------------------------------- migrate ----

INSERT INTO estimate_beam_types (
    estimate_id, label, kind, width_in, height_in,
    top_bars_count, top_bars_size, bottom_bars_count, bottom_bars_size,
    mid_bars_count, mid_bars_size, stirrup_size, stirrup_spacing_in,
    l_bars_count, l_bars_size, l_bars_spacing_in, pt_cables_count, sort_order
)
SELECT DISTINCT ON (
        m.estimate_id, gb.kind, gb.width_in, gb.height_in,
        gb.top_bars_count, gb.top_bars_size, gb.bottom_bars_count, gb.bottom_bars_size,
        gb.mid_bars_count, gb.mid_bars_size, gb.stirrup_size, gb.stirrup_spacing_in,
        gb.l_bars_count, gb.l_bars_size, gb.l_bars_spacing_in, gb.pt_cables_count)
    m.estimate_id, gb.label, gb.kind, gb.width_in, gb.height_in,
    gb.top_bars_count, gb.top_bars_size, gb.bottom_bars_count, gb.bottom_bars_size,
    gb.mid_bars_count, gb.mid_bars_size, gb.stirrup_size, gb.stirrup_spacing_in,
    gb.l_bars_count, gb.l_bars_size, gb.l_bars_spacing_in, gb.pt_cables_count,
    min(gb.sort_order) OVER (PARTITION BY m.estimate_id, gb.label)
FROM grade_beams gb
JOIN mono_slabs m ON m.id = gb.mono_slab_id
ORDER BY
    m.estimate_id, gb.kind, gb.width_in, gb.height_in,
    gb.top_bars_count, gb.top_bars_size, gb.bottom_bars_count, gb.bottom_bars_size,
    gb.mid_bars_count, gb.mid_bars_size, gb.stirrup_size, gb.stirrup_spacing_in,
    gb.l_bars_count, gb.l_bars_size, gb.l_bars_spacing_in, gb.pt_cables_count,
    gb.created_at;

-- ------------------------------------------------------------ link pours ----

ALTER TABLE grade_beams
    ADD COLUMN IF NOT EXISTS beam_type_id uuid
    REFERENCES estimate_beam_types(id) ON DELETE CASCADE;

UPDATE grade_beams gb
SET beam_type_id = t.id
FROM mono_slabs m, estimate_beam_types t
WHERE m.id = gb.mono_slab_id
  AND t.estimate_id = m.estimate_id
  AND t.kind = gb.kind
  AND t.width_in = gb.width_in
  AND t.height_in = gb.height_in
  AND t.top_bars_count     IS NOT DISTINCT FROM gb.top_bars_count
  AND t.top_bars_size      IS NOT DISTINCT FROM gb.top_bars_size
  AND t.bottom_bars_count  IS NOT DISTINCT FROM gb.bottom_bars_count
  AND t.bottom_bars_size   IS NOT DISTINCT FROM gb.bottom_bars_size
  AND t.mid_bars_count     IS NOT DISTINCT FROM gb.mid_bars_count
  AND t.mid_bars_size      IS NOT DISTINCT FROM gb.mid_bars_size
  AND t.stirrup_size       IS NOT DISTINCT FROM gb.stirrup_size
  AND t.stirrup_spacing_in IS NOT DISTINCT FROM gb.stirrup_spacing_in
  AND t.l_bars_count       IS NOT DISTINCT FROM gb.l_bars_count
  AND t.l_bars_size        IS NOT DISTINCT FROM gb.l_bars_size
  AND t.l_bars_spacing_in  IS NOT DISTINCT FROM gb.l_bars_spacing_in
  AND t.pt_cables_count    IS NOT DISTINCT FROM gb.pt_cables_count;

DO $$
DECLARE
    orphan int; types int; usages int;
BEGIN
    SELECT count(*) INTO orphan FROM grade_beams WHERE beam_type_id IS NULL;
    IF orphan > 0 THEN
        RAISE EXCEPTION 'Aborting: % beam row(s) did not match a type', orphan;
    END IF;
    SELECT count(*) INTO types FROM estimate_beam_types;
    SELECT count(*) INTO usages FROM grade_beams;
    RAISE NOTICE 'migrated: % types, % pour usages', types, usages;
END $$;

ALTER TABLE grade_beams ALTER COLUMN beam_type_id SET NOT NULL;

-- ------------------------------------------- drop what moved to the type ----

ALTER TABLE grade_beams
    DROP COLUMN IF EXISTS kind,
    DROP COLUMN IF EXISTS label,
    DROP COLUMN IF EXISTS width_in,
    DROP COLUMN IF EXISTS height_in,
    DROP COLUMN IF EXISTS top_bars_count,
    DROP COLUMN IF EXISTS top_bars_size,
    DROP COLUMN IF EXISTS bottom_bars_count,
    DROP COLUMN IF EXISTS bottom_bars_size,
    DROP COLUMN IF EXISTS mid_bars_count,
    DROP COLUMN IF EXISTS mid_bars_size,
    DROP COLUMN IF EXISTS stirrup_size,
    DROP COLUMN IF EXISTS stirrup_spacing_in,
    DROP COLUMN IF EXISTS l_bars_count,
    DROP COLUMN IF EXISTS l_bars_size,
    DROP COLUMN IF EXISTS l_bars_spacing_in,
    DROP COLUMN IF EXISTS pt_cables_count;

CREATE INDEX IF NOT EXISTS grade_beams_beam_type_idx ON grade_beams (beam_type_id);

COMMENT ON TABLE grade_beams IS
    'How much of a beam type a pour uses. The section and bar schedule live on '
    'estimate_beam_types.';

-- ------------------------------------------------------------------ view ----

-- Joined shape for the rollups and drivers that filter on kind.
CREATE OR REPLACE VIEW grade_beam_details AS
SELECT
    gb.id, gb.mono_slab_id, gb.beam_type_id, gb.length_lf, gb.notes,
    gb.sort_order, gb.created_at, gb.updated_at,
    gb.calc_rebar_lb, gb.calc_pt_cable_lf, gb.calc_concrete_cy, gb.calc_poly_sf,
    t.estimate_id, t.label, t.kind, t.width_in, t.height_in,
    t.top_bars_count, t.top_bars_size, t.bottom_bars_count, t.bottom_bars_size,
    t.mid_bars_count, t.mid_bars_size, t.stirrup_size, t.stirrup_spacing_in,
    t.l_bars_count, t.l_bars_size, t.l_bars_spacing_in, t.pt_cables_count
FROM grade_beams gb
JOIN estimate_beam_types t ON t.id = gb.beam_type_id;

COMMENT ON VIEW grade_beam_details IS
    'grade_beams joined to its estimate_beam_types row — the pre-025 column shape.';

COMMIT;
