-- 084_daily_reports.sql
--
-- Daily reports from the field, in the app instead of Jotform → Notion.
--
-- Chad, 2026-09-09: "this is a daily reports for projects.. right now we use
-- jotform then import into notion", then "I think we need to just import
-- everything from jotform then set a form page to fill out here instead of
-- the extra step of importing"; on the proposal, "build it".
--
-- What the foremen fill in today is Jotform form 210626162682150 ("S and S
-- Daily Construction Report", bilingual, in use since 2021-03; an older
-- 12-question form 210135509985156 carried Jan–Mar 2021). The morning timer
-- on the office box copied each submission into a Notion database. Both of
-- those go: every submission of both forms is imported here once (and hourly
-- until the crews move over), and the same report is a phone-sized page in
-- the app, English and Spanish, for people signed in with the new `foreman`
-- role — who see nothing else of the app.
--
-- field_jobs and field_foremen are the two pick-lists the form offers, the
-- way the Jotform dropdowns did: seeded here with the dropdowns as they
-- stand on 2026-09-09, added to by the import for every name it meets (those
-- inactive), and kept by the office from the Daily reports page. A job may
-- point at the project it is; nothing depends on it.
--
-- daily_reports is the report: the day, the job, the foremen (the Jotform
-- field allowed several), the four texts (the old form's issues/progress
-- and comments folded into delays and comments), the pour — poured yes/no,
-- yards, supplier, what — tax exempt, the maintenance checks, and where it
-- came from: 'app', or 'jotform' with the form and submission ids (the
-- submission id unique, so the hourly pull cannot double a report).
-- daily_report_crew is the man-power grid, one row per trade; the sub-labor
-- grid is daily_report_subs. Each row keeps workers and hours as entered and
-- a man_hours figure the totals use: the app form asks hours EACH, so
-- workers × hours; the Jotform grids were filled both ways over the years
-- (2021: "3 workers, 30 hrs"; 2026: "12 workers, 8 hrs"), so the import
-- reads hours over sixteen as a day's total for the row and anything else
-- as hours each. Nobody works a seventeen-hour day.

ALTER TABLE estimators DROP CONSTRAINT IF EXISTS estimators_role_check;
ALTER TABLE estimators
    ADD CONSTRAINT estimators_role_check
    CHECK (role IN ('admin', 'senior_estimator', 'estimator', 'user', 'foreman'));
COMMENT ON COLUMN estimators.role IS
    'admin | senior_estimator | estimator | user — each includes the ones after it — or foreman, who only files daily reports; app/policy.py enforces';

CREATE TABLE IF NOT EXISTS field_jobs (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    project_id  uuid REFERENCES projects (id) ON DELETE SET NULL,
    is_active   boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  uuid REFERENCES estimators (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS field_jobs_name_key ON field_jobs (lower(name));
COMMENT ON TABLE field_jobs IS 'The jobs the daily report form offers (sql/084); inactive ones stay for the old reports.';

CREATE TABLE IF NOT EXISTS field_foremen (
    id            serial PRIMARY KEY,
    name          text NOT NULL,
    estimator_id  uuid REFERENCES estimators (id) ON DELETE SET NULL,
    is_active     boolean NOT NULL DEFAULT true,
    sort_order    integer NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid REFERENCES estimators (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS field_foremen_name_key ON field_foremen (lower(name));
COMMENT ON TABLE field_foremen IS 'The foremen the daily report form offers (sql/084); estimator_id when the person has a sign-in.';

CREATE TABLE IF NOT EXISTS daily_reports (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date            date NOT NULL,
    job_id                 integer NOT NULL REFERENCES field_jobs (id),
    foremen                text[] NOT NULL DEFAULT '{}',
    work_accomplished      text,
    delays                 text,
    plan_tomorrow          text,
    safety_concerns        text,
    comments               text,
    concrete_poured        boolean NOT NULL DEFAULT false,
    yards_poured           numeric(10, 2),
    supplier               text,
    what_poured            text,
    tax_exempt             boolean,
    maintenance            text[] NOT NULL DEFAULT '{}',
    source                 text NOT NULL DEFAULT 'app' CHECK (source IN ('app', 'jotform')),
    jotform_form_id        text,
    jotform_submission_id  text,
    signature_url          text,
    import_fingerprint     text,
    submitted_at           timestamptz NOT NULL DEFAULT now(),
    submitted_by           uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    updated_by             uuid REFERENCES estimators (id) ON DELETE SET NULL,
    CONSTRAINT daily_reports_yards_check CHECK (yards_poured IS NULL OR yards_poured >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS daily_reports_jotform_key
    ON daily_reports (jotform_submission_id) WHERE jotform_submission_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS daily_reports_date_idx ON daily_reports (report_date DESC, submitted_at DESC);
CREATE INDEX IF NOT EXISTS daily_reports_job_idx ON daily_reports (job_id, report_date);
COMMENT ON TABLE daily_reports IS 'A day on a job from the foreman (sql/084): from the app form, or imported from Jotform by submission id.';
COMMENT ON COLUMN daily_reports.maintenance IS 'The checks done, as keys: fuel | grease | oil | hydraulic | tires.';
COMMENT ON COLUMN daily_reports.import_fingerprint IS 'Hash of what the Jotform import last wrote; a report edited here since is left alone on a rerun.';

CREATE TABLE IF NOT EXISTS daily_report_crew (
    id         serial PRIMARY KEY,
    report_id  uuid NOT NULL REFERENCES daily_reports (id) ON DELETE CASCADE,
    trade      text NOT NULL CHECK (trade IN ('foreman', 'assistants', 'rod_busters', 'form_setters', 'finishers', 'laborers')),
    workers    integer NOT NULL DEFAULT 0 CHECK (workers >= 0),
    hours      numeric(8, 2) NOT NULL DEFAULT 0 CHECK (hours >= 0),
    man_hours  numeric(10, 2) NOT NULL DEFAULT 0,
    UNIQUE (report_id, trade)
);
COMMENT ON TABLE daily_report_crew IS 'The man-power grid (sql/084): hours as entered, man_hours what the totals use.';

CREATE TABLE IF NOT EXISTS daily_report_subs (
    id          serial PRIMARY KEY,
    report_id   uuid NOT NULL REFERENCES daily_reports (id) ON DELETE CASCADE,
    sort_order  integer NOT NULL DEFAULT 0,
    trade       text NOT NULL CHECK (trade IN ('finishers', 'form_setters', 'rod_busters', 'laborers')),
    sub_name    text NOT NULL,
    workers     integer NOT NULL DEFAULT 0 CHECK (workers >= 0),
    hours       numeric(8, 2) NOT NULL DEFAULT 0 CHECK (hours >= 0),
    man_hours   numeric(10, 2) NOT NULL DEFAULT 0
);
COMMENT ON TABLE daily_report_subs IS 'The sub-labor grid (sql/084): a subcontractor''s crew on the job that day.';

-- Every foreign key a delete can travel through has an index (sql/067's rule, tests/test_fk_indexes.py).
CREATE INDEX IF NOT EXISTS field_jobs_project_id_idx ON field_jobs (project_id);
CREATE INDEX IF NOT EXISTS field_jobs_updated_by_idx ON field_jobs (updated_by);
CREATE INDEX IF NOT EXISTS field_foremen_estimator_id_idx ON field_foremen (estimator_id);
CREATE INDEX IF NOT EXISTS field_foremen_updated_by_idx ON field_foremen (updated_by);
CREATE INDEX IF NOT EXISTS daily_reports_submitted_by_idx ON daily_reports (submitted_by);
CREATE INDEX IF NOT EXISTS daily_reports_updated_by_idx ON daily_reports (updated_by);
CREATE INDEX IF NOT EXISTS daily_report_subs_report_id_idx ON daily_report_subs (report_id);

-- The two pick-lists as the Jotform dropdowns stand on 2026-09-09.
INSERT INTO field_jobs (name, sort_order)
SELECT v.name, v.n FROM (VALUES
    ('TCU SITE D', 1), ('OHT AMBASSADOR', 2), ('SOUTHSTONE YARD', 3), ('PROJECT X EAST', 4),
    ('PROJECT X WEST', 5), ('VIRIDIAN III', 6), ('WALSH RANCH', 7), ('NORTHWEST VILLAGE', 8),
    ('BUCKLEY', 9), ('HIDDEN COVE', 10), ('MANHEIM DALLAS', 11), ('Mardel', 12), ('PARK LANE', 13),
    ('MANHIEM FT', 14), ('Office', 15)
) AS v (name, n)
WHERE NOT EXISTS (SELECT 1 FROM field_jobs f WHERE lower(f.name) = lower(v.name));

INSERT INTO field_foremen (name, sort_order)
SELECT v.name, v.n FROM (VALUES
    ('Adan(Rocky)', 1), ('Benito', 2), ('Jorge', 3), ('Jose G', 4), ('Pedro', 5),
    ('Daniel', 6), ('Marco', 7), ('Juan Carlos', 8), ('Isaias', 9), ('Rene', 10)
) AS v (name, n)
WHERE NOT EXISTS (SELECT 1 FROM field_foremen f WHERE lower(f.name) = lower(v.name));
