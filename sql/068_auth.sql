-- 068_auth.sql
--
-- Logins. Chad, 2026-09-07: "I want admin, senior estimator, estimator and
-- user.. senior estimator can change pricing, user can only view. admin has
-- access to add, delete, users and full control."
--
-- Until now the API had no login and CORS was a wildcard: on the LAN anyone
-- could change a price or delete a job, and any website open in a browser
-- while the server ran could drive the API. (README, run.ps1, and the app note
-- all said so; "largest open risk" since 2026-08.)
--
-- estimators gets a password hash — scrypt, written by backend/set_password.py
-- or by an admin from the estimators screen; NULL means the person cannot sign
-- in yet — and the four roles replace admin | estimator | viewer (the one
-- 'viewer' the old CHECK allowed is now 'user'). Each role includes the ones
-- below it: user views; estimator does takeoffs; senior estimator also sets
-- prices, rates, quotes, rules and markup; admin also manages people and
-- deletes whole jobs. app/policy.py is the one place that says which route
-- needs which.
--
-- sessions holds who is signed in. The cookie carries a random token; the
-- table holds its SHA-256, so a copy of the table is not a set of keys. Idle
-- 12 hours, absolute 30 days, enforced in app/auth.py.

ALTER TABLE estimators ADD COLUMN IF NOT EXISTS password_hash text;
COMMENT ON COLUMN estimators.password_hash IS
    'scrypt$N$r$p$salt$key (app/auth.py). NULL: cannot sign in.';

UPDATE estimators SET role = 'user' WHERE role = 'viewer';
ALTER TABLE estimators DROP CONSTRAINT IF EXISTS estimators_role_check;
ALTER TABLE estimators
    ADD CONSTRAINT estimators_role_check
    CHECK (role IN ('admin', 'senior_estimator', 'estimator', 'user'));
COMMENT ON COLUMN estimators.role IS
    'admin | senior_estimator | estimator | user — each includes the ones after it; app/policy.py enforces';

CREATE TABLE IF NOT EXISTS sessions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimator_id  uuid NOT NULL REFERENCES estimators (id) ON DELETE CASCADE,
    token_hash    text NOT NULL UNIQUE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    user_agent    text,
    ip            text
);
CREATE INDEX IF NOT EXISTS sessions_estimator_id_idx ON sessions (estimator_id);
COMMENT ON TABLE sessions IS 'Signed-in sessions (sql/068). token_hash is the SHA-256 of the cookie value.';
