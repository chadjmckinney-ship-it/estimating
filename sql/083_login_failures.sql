-- 083_login_failures.sql
--
-- A sign-in lockout, before the app is reachable from outside the office.
--
-- Chad, 2026-09-09: the field foremen will fill in the daily report from
-- their phones, and the office router cannot be opened (a Netgear Nighthawk
-- whose admin password nobody has), so the app is being published through
-- Tailscale Funnel under a public https name. Until now the login box could
-- be tried forever: nothing counted a wrong password, each try cost the
-- server ~150 ms of scrypt and the guesser nothing. On the LAN that was the
-- office; on the internet it is everyone.
--
-- Every failed sign-in leaves a row here: the name as typed (lowercased,
-- known or not) and the address it came from. app/auth.py counts them over
-- the last fifteen minutes: five for a name, or twenty from one address,
-- lock that name or address until fifteen minutes after the fifth (or the
-- twentieth), and a locked try is refused with a 429 and a Retry-After
-- before the password is even looked at, so it neither costs the scrypt nor
-- counts as another failure. A sign-in that succeeds clears the name's rows;
-- rows older than a day go with the next failure's housekeeping.
--
-- The same commit puts /docs, /redoc and /openapi.json behind a session:
-- they listed every route to anyone who could reach the port.

CREATE TABLE IF NOT EXISTS login_failures (
    id         bigserial PRIMARY KEY,
    username   text NOT NULL,
    ip         text,
    failed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS login_failures_username_idx ON login_failures (username, failed_at);
CREATE INDEX IF NOT EXISTS login_failures_ip_idx ON login_failures (ip, failed_at);
COMMENT ON TABLE login_failures IS
    'Failed sign-ins (sql/083). app/auth.py locks a name after 5 in 15 minutes and an address after 20; a success clears the name.';
COMMENT ON COLUMN login_failures.username IS 'As typed, lowercased and trimmed; need not be a real username.';
