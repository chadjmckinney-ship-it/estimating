-- 067_fk_indexes.sql
--
-- An index under every foreign key that can be deleted through.
--
-- Sixteen foreign-key columns had no index: who created a project, which
-- estimator owns an estimate, the mix a pour / pier group / wall run / column
-- type / deck level points at, the section's footing mix and its two vapor
-- materials, the material behind a forming line, the machine behind an
-- equipment line, the beam type a deck-level beam uses, and the two on the
-- (unbuilt) import table. Irrelevant at today's row counts — twenty pours,
-- seventeen wall runs — but a DELETE or an UPDATE of the referenced key is a
-- sequential scan of every one of these tables per row, and a catalog that
-- is only ever deactivated today will not stay that way (audit 2026-09-04,
-- P3; batch 4 on Chad's "restarted, lets do batch 4", 2026-09-06).
--
-- Left alone on purpose: the twenty bar-size columns that point at
-- bar_weights (sql/066). Nothing deletes a bar size, the column holds one of
-- a dozen values, and an index on it is dead weight on every write.
-- tests/test_fk_indexes.py names that exception and refuses any other.

CREATE INDEX IF NOT EXISTS projects_created_by_idx               ON projects (created_by);
CREATE INDEX IF NOT EXISTS estimates_estimator_id_idx            ON estimates (estimator_id);
CREATE INDEX IF NOT EXISTS etakeoff_imports_estimate_id_idx      ON etakeoff_imports (estimate_id);
CREATE INDEX IF NOT EXISTS etakeoff_imports_imported_by_idx      ON etakeoff_imports (imported_by);
CREATE INDEX IF NOT EXISTS estimate_sections_footing_mix_idx     ON estimate_sections (footing_mix_design_id);
CREATE INDEX IF NOT EXISTS estimate_sections_vapor_barrier_idx   ON estimate_sections (vapor_barrier_material_id);
CREATE INDEX IF NOT EXISTS estimate_sections_vapor_tape_idx      ON estimate_sections (vapor_tape_material_id);
CREATE INDEX IF NOT EXISTS mono_slabs_mix_design_id_idx          ON mono_slabs (mix_design_id);
CREATE INDEX IF NOT EXISTS pier_groups_mix_design_id_idx         ON pier_groups (mix_design_id);
CREATE INDEX IF NOT EXISTS wall_runs_mix_design_id_idx           ON wall_runs (mix_design_id);
CREATE INDEX IF NOT EXISTS wall_runs_footing_mix_design_id_idx   ON wall_runs (footing_mix_design_id);
CREATE INDEX IF NOT EXISTS column_types_mix_design_id_idx        ON column_types (mix_design_id);
CREATE INDEX IF NOT EXISTS deck_levels_mix_design_id_idx         ON deck_levels (mix_design_id);
CREATE INDEX IF NOT EXISTS deck_level_beams_beam_type_id_idx     ON deck_level_beams (beam_type_id);
CREATE INDEX IF NOT EXISTS estimate_forming_lines_material_idx   ON estimate_forming_lines (material_id);
CREATE INDEX IF NOT EXISTS estimate_equipment_lines_equip_idx    ON estimate_equipment_lines (equipment_id);
