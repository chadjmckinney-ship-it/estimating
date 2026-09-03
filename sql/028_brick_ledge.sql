-- 028: brick ledge as its own beam kind
--
-- A brick ledge is an edge condition, not a beam, and modelling it as a grade
-- beam charges the estimate for things that are not there. On the LBJ job the
-- 6"x32" adder booked 4,427 SF of poly and 3,536 lb of steel that do not exist:
-- widening a beam from 12" to 18" leaves it with the same two sides at the same
-- height, and a wider cage needs longer stirrup legs (~234 lb across 830 LF),
-- not a second cage. The concrete — 43.45 CY — is real and stays.
--
-- The other case the old model could not express at all: a ledge that does not
-- widen the beam, only adds forming. That is width 0, height 0, and a form face.
--
-- Rules for kind = 'brick_ledge', in app/services:
--   concrete   width x height x LF (0 width = no concrete)
--   poly       none — the beam's sides are unchanged
--   bar schedule  whatever is entered; usually none
--   forming    a 2x6 along the length, ply facing the form_face_in depth
--
-- form_face_in is the depth that actually gets ply-faced, which is not the same
-- as the concrete depth: a thickening of a trenched beam is only formed above
-- grade. NULL falls back to height_in.

BEGIN;

ALTER TABLE estimate_beam_types
    DROP CONSTRAINT IF EXISTS estimate_beam_types_kind_check;

ALTER TABLE estimate_beam_types
    ADD CONSTRAINT estimate_beam_types_kind_check
    CHECK (kind IN ('grade_beam', 'exposed', 'drop', 'brick_ledge'));

-- A ledge with no thickening is 0 x 0. Every other kind still needs a section.
ALTER TABLE estimate_beam_types
    DROP CONSTRAINT IF EXISTS estimate_beam_types_width_in_check,
    DROP CONSTRAINT IF EXISTS estimate_beam_types_height_in_check;

ALTER TABLE estimate_beam_types
    ADD CONSTRAINT estimate_beam_types_width_in_check
    CHECK (width_in > 0 OR (kind = 'brick_ledge' AND width_in >= 0)),
    ADD CONSTRAINT estimate_beam_types_height_in_check
    CHECK (height_in > 0 OR (kind = 'brick_ledge' AND height_in >= 0));

ALTER TABLE estimate_beam_types
    ADD COLUMN IF NOT EXISTS form_face_in numeric(8, 3)
    CHECK (form_face_in IS NULL OR form_face_in >= 0);

COMMENT ON COLUMN estimate_beam_types.form_face_in IS
    'Depth of form face that gets ply, for brick ledge. NULL = height_in.';

-- grade_beam_details is the joined shape the rollups read; recreate it so the
-- new column comes through.
DROP VIEW IF EXISTS grade_beam_details;

CREATE VIEW grade_beam_details AS
SELECT
    gb.id,
    gb.mono_slab_id,
    gb.beam_type_id,
    gb.length_lf,
    gb.notes,
    gb.sort_order,
    gb.created_at,
    gb.updated_at,
    gb.calc_rebar_lb,
    gb.calc_pt_cable_lf,
    gb.calc_concrete_cy,
    gb.calc_poly_sf,
    t.estimate_id,
    t.label,
    t.kind,
    t.width_in,
    t.height_in,
    t.form_face_in,
    t.top_bars_count,
    t.top_bars_size,
    t.bottom_bars_count,
    t.bottom_bars_size,
    t.mid_bars_count,
    t.mid_bars_size,
    t.stirrup_size,
    t.stirrup_spacing_in,
    t.l_bars_count,
    t.l_bars_size,
    t.l_bars_spacing_in,
    t.pt_cables_count
FROM grade_beams gb
JOIN estimate_beam_types t ON t.id = gb.beam_type_id;

COMMIT;
