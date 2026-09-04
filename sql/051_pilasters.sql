-- 051 — pilasters: how many faces of a column type are actually formed
--
-- A pilaster is a short column, and Chad takes them off on the column sheet
-- for exactly that reason (sql/041):
--
--   "I dont use the pilaster section because it doesnt let me add enough info
--    and I just use column sheet for it since it is basically a short column…
--    so when we create columns we can just make 2 and call the second section
--    pilasters."
--
-- So pilasters are a second section of kind `columns`, and almost nothing
-- needed building for them. This is the one thing that did.
--
-- ---------------------------------------------------------------------------
-- Why it matters more than it looks
-- ---------------------------------------------------------------------------
--
-- A free-standing column is WRAPPED — all four faces. A pilaster sits against
-- a wall, so one or two of those faces are somebody else's form or no form at
-- all. `columns.form_sf` is contact area AND the basis this section allocates
-- every shared cost by (sql/045), so getting the face count wrong does not
-- just misprice plywood: it moves four labor lines, the nails, and the share
-- of supervision, equipment and contract services the section carries.
--
-- On an 18×24 at 12 ft that is 84 SF wrapped against 60 SF on a wall — a 29%
-- swing in the number everything else rides.
--
-- Chad, 2026-09-02, asked whether a pilaster is three faces, two, or four:
-- **"varies by job — make it an input."** So it is a per-type field, not a
-- constant and not a section-level switch: one section can hold pilasters
-- that sit differently on different walls.
--
-- ---------------------------------------------------------------------------
-- The convention, which the grid and the API both state
-- ---------------------------------------------------------------------------
--
-- The unformed face is always an **L** face. Enter L as the dimension ALONG
-- the wall and W as the projection out of it, and the arithmetic follows:
--
--   4  free-standing column      2L + 2W    4 chamfered corners
--   3  pilaster on a built wall   L + 2W    2   — the wall side needs no form
--   2  monolithic with the wall      2W     2   — the wall's gang form carries
--                                                  the outer face; the two
--                                                  returns are ours
--
-- Corners follow the same fact: a face against a wall has no chamfer strip on
-- it. Four exposed corners when wrapped, two when it is against anything.
--
-- Default 4, so every existing row is a column and no number moves. The LBJ
-- columns section is 68 wrapped columns and reads the same after this.
--
-- ---------------------------------------------------------------------------
-- Left open on purpose: whether the WALL already carries the concrete
-- ---------------------------------------------------------------------------
--
-- Asked the same day whether a wall run's CY already includes the pilaster it
-- passes through, Chad: "not sure — I'd have to look at a job." So this
-- migration does NOT net anything out. A pilaster type carries its own full
-- L × W × height, which is the honest reading of the schedule in front of you,
-- and the columns screen warns when a section holds wall-side types so the
-- overlap is checked against a real takeoff rather than assumed either way.
--
-- Do not "fix" that by deducting until a job has settled it. Silently removing
-- concrete somebody entered is the worse of the two errors.

ALTER TABLE column_types
    ADD COLUMN IF NOT EXISTS formed_faces smallint NOT NULL DEFAULT 4;

ALTER TABLE column_types
    DROP CONSTRAINT IF EXISTS column_types_formed_faces_ck;

ALTER TABLE column_types
    ADD CONSTRAINT column_types_formed_faces_ck
    CHECK (formed_faces IN (2, 3, 4));

COMMENT ON COLUMN column_types.formed_faces IS
    'How many faces are formed: 4 = free-standing column (2L+2W, 4 corners); '
    '3 = pilaster on a built wall (L+2W, 2 corners); 2 = monolithic with the '
    'wall, returns only (2W, 2 corners). The unformed face is always an L '
    'face, so enter L along the wall and W as the projection. Drives '
    'calc_form_sf, which is also this section''s allocation basis.';
