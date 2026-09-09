-- 085_management.sql
--
-- A management role, and management notes on a daily report.
--
-- Chad, 2026-09-09: "in daily reports.. we want to add another field only
-- visible by senior estimators and above.. called management notes.. and
-- add a management roll basically a copy of senior estimator".
--
-- management stands beside senior_estimator on the ladder, not above it:
-- the same rights and the same refusals (app/policy.py ranks them equal).
-- management_notes is read back only to senior estimators, management and
-- admins, and only they may write it; everyone else, the foremen included,
-- gets the report without it. The Jotform import never touches it.

ALTER TABLE estimators DROP CONSTRAINT IF EXISTS estimators_role_check;
ALTER TABLE estimators
    ADD CONSTRAINT estimators_role_check
    CHECK (role IN ('admin', 'senior_estimator', 'management', 'estimator', 'user', 'foreman'));
COMMENT ON COLUMN estimators.role IS
    'admin | senior_estimator = management | estimator | user — each includes the ones after it — or foreman, who only files daily reports; app/policy.py enforces';

ALTER TABLE daily_reports ADD COLUMN IF NOT EXISTS management_notes text;
COMMENT ON COLUMN daily_reports.management_notes IS
    'For senior estimators, management and admins only (sql/085); the API blanks it for everyone else.';
