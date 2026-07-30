-- Expand estimators: roles, contact fields
-- Apply: psql -d estimating -f sql/003_estimators_expand.sql

BEGIN;

-- Role: Admin can manage rates/catalogs; Estimator creates bids; Viewer read-only (app-enforced later)
ALTER TABLE estimators
    ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'estimator',
    ADD COLUMN IF NOT EXISTS phone text,
    ADD COLUMN IF NOT EXISTS title text,
    ADD COLUMN IF NOT EXISTS notes text,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- Backfill safety if column existed without constraint
ALTER TABLE estimators DROP CONSTRAINT IF EXISTS estimators_role_check;
ALTER TABLE estimators
    ADD CONSTRAINT estimators_role_check
    CHECK (role IN ('admin', 'estimator', 'viewer'));

COMMENT ON COLUMN estimators.role IS 'admin | estimator | viewer — app enforces permissions later';
COMMENT ON COLUMN estimators.phone IS 'Office or mobile';
COMMENT ON COLUMN estimators.title IS 'Job title e.g. Senior Estimator';

-- Seed default admin (idempotent on username)
INSERT INTO estimators (username, full_name, email, role, title, is_active)
VALUES ('chad', 'Chad', NULL, 'admin', 'Administrator', true)
ON CONFLICT (username) DO UPDATE SET
    role = EXCLUDED.role,
    title = EXCLUDED.title,
    is_active = true,
    updated_at = now();

COMMIT;
