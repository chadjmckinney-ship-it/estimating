-- 069_audit.sql
--
-- Who changed what (Chad, 2026-09-07: "lets do the audit stamps").
--
-- Two layers. audit_log is every write request that reached the API — who,
-- when, which route, the JSON they sent (password fields blanked, sign-in
-- bodies never kept), the status it got and how long it took — written by
-- app/audit.py's middleware, so a route that writes through raw SQL is
-- covered the same as one that writes through the ORM. That answers "who
-- changed the price of the 3000 mix last week" without the code knowing
-- anything about mix designs.
--
-- updated_by on every input table is the row's own answer to "who last
-- touched this": set by a flush hook for ORM writes and by hand in the three
-- raw-SQL writers (job rules, section rates, company settings). A recalc
-- rewriting calc_* columns does NOT restamp a row — a company setting change
-- reprices every pour in the office, and that is the setting's author, not
-- the pour's. assembly_rates and pier_drill_rates are left alone: nothing
-- but a migration writes them.
--
-- Every new foreign key gets its index (sql/067's rule).

CREATE TABLE IF NOT EXISTS audit_log (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    at            timestamptz NOT NULL DEFAULT now(),
    estimator_id  uuid REFERENCES estimators (id) ON DELETE SET NULL,
    username      text,
    method        text NOT NULL,
    path          text NOT NULL,
    status        integer NOT NULL,
    body          jsonb,
    duration_ms   integer,
    ip            text
);
CREATE INDEX IF NOT EXISTS audit_log_at_idx           ON audit_log (at DESC);
CREATE INDEX IF NOT EXISTS audit_log_estimator_id_idx ON audit_log (estimator_id);
CREATE INDEX IF NOT EXISTS audit_log_path_idx         ON audit_log (path);
COMMENT ON TABLE audit_log IS
    'Every write request that reached the API (sql/069): who, when, route, redacted body, status.';

ALTER TABLE column_types             ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE concrete_suppliers       ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE deck_level_beams         ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE deck_levels              ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE equipment                ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_beam_types      ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_equipment_lines ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_forming_lines   ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_labor_lines     ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_prices          ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_rules           ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimate_sections        ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimates                ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE estimators               ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE grade_beams              ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE materials                ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE mix_designs              ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE mono_slabs               ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE pier_groups              ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE projects                 ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE section_quotes           ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE section_rates            ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE system_settings          ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;
ALTER TABLE wall_runs                ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES estimators (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS column_types_updated_by_idx             ON column_types (updated_by);
CREATE INDEX IF NOT EXISTS concrete_suppliers_updated_by_idx       ON concrete_suppliers (updated_by);
CREATE INDEX IF NOT EXISTS deck_level_beams_updated_by_idx         ON deck_level_beams (updated_by);
CREATE INDEX IF NOT EXISTS deck_levels_updated_by_idx              ON deck_levels (updated_by);
CREATE INDEX IF NOT EXISTS equipment_updated_by_idx                ON equipment (updated_by);
CREATE INDEX IF NOT EXISTS estimate_beam_types_updated_by_idx      ON estimate_beam_types (updated_by);
CREATE INDEX IF NOT EXISTS estimate_equipment_lines_updated_by_idx ON estimate_equipment_lines (updated_by);
CREATE INDEX IF NOT EXISTS estimate_forming_lines_updated_by_idx   ON estimate_forming_lines (updated_by);
CREATE INDEX IF NOT EXISTS estimate_labor_lines_updated_by_idx     ON estimate_labor_lines (updated_by);
CREATE INDEX IF NOT EXISTS estimate_prices_updated_by_idx          ON estimate_prices (updated_by);
CREATE INDEX IF NOT EXISTS estimate_rules_updated_by_idx           ON estimate_rules (updated_by);
CREATE INDEX IF NOT EXISTS estimate_sections_updated_by_idx        ON estimate_sections (updated_by);
CREATE INDEX IF NOT EXISTS estimates_updated_by_idx                ON estimates (updated_by);
CREATE INDEX IF NOT EXISTS estimators_updated_by_idx               ON estimators (updated_by);
CREATE INDEX IF NOT EXISTS grade_beams_updated_by_idx              ON grade_beams (updated_by);
CREATE INDEX IF NOT EXISTS materials_updated_by_idx                ON materials (updated_by);
CREATE INDEX IF NOT EXISTS mix_designs_updated_by_idx              ON mix_designs (updated_by);
CREATE INDEX IF NOT EXISTS mono_slabs_updated_by_idx               ON mono_slabs (updated_by);
CREATE INDEX IF NOT EXISTS pier_groups_updated_by_idx              ON pier_groups (updated_by);
CREATE INDEX IF NOT EXISTS projects_updated_by_idx                 ON projects (updated_by);
CREATE INDEX IF NOT EXISTS section_quotes_updated_by_idx           ON section_quotes (updated_by);
CREATE INDEX IF NOT EXISTS section_rates_updated_by_idx            ON section_rates (updated_by);
CREATE INDEX IF NOT EXISTS system_settings_updated_by_idx          ON system_settings (updated_by);
CREATE INDEX IF NOT EXISTS wall_runs_updated_by_idx                ON wall_runs (updated_by);
