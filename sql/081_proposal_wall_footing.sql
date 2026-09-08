-- 081_proposal_wall_footing.sql
--
-- Walls and their footings as separate proposal lines. Chad, 2026-09-08, on
-- the first proposal: "first, walls and footings section on the proposal.. I
-- want the walls and associated footings separate" — and, on the proposal,
-- "build it". docs/specs/proposal-spec.md.
--
-- The costing already keeps the split (sql/042): every wall run stores what
-- the wall costs and sells on its form feet and what the footing under it
-- costs and sells on its plan area, computed so the two always add up to the
-- run. The proposal seeded one line from the run and hid it. Now a run seeds
-- two — the wall in FF at the wall's rate, the footing in LF at the footing's
-- rate — and each line remembers WHICH half of the run it is, so a refresh
-- re-reads both and keeps the words on each. A run with no footing gets the
-- wall line only.
--
-- Spot footings sell per footing (sql/072) and always did in the costing;
-- the section's UNIT label defaulted to SF because the kind had no entry in
-- DEFAULT_UNIT_BY_KIND. The default is EA now, and a section still wearing
-- the wrong default is set right.

ALTER TABLE proposal_lines
    ADD COLUMN IF NOT EXISTS source_part text
        CHECK (source_part IS NULL OR source_part IN ('wall', 'footing'));

COMMENT ON COLUMN proposal_lines.source_part IS
    'Which half of a wall run this line is (sql/081): wall or footing. NULL on every other '
    'line. A refresh matches a line on (source_table, source_id, source_part).';

UPDATE estimate_sections
   SET unit = 'EA'
 WHERE kind = 'spot_footings' AND unit = 'SF';
