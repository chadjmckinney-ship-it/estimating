# Public access for the field, and what the app changed for it (2026-09-09)

## Why

The daily report is moving into the app: the foremen will fill it in from
their phones instead of Jotform (Chad, 2026-09-09: "just import everything
from jotform then set a form page to fill out here instead of the extra step
of importing"). A phone on a job site is not on the office LAN, so the app
needs an address the internet can reach.

Port-forwarding on the office router was the first idea and is not
available: the router is a Netgear Nighthawk whose admin password and
security questions nobody has. Tailscale Funnel does the same job without
touching the router. The box joins Chad's tailnet (which already has
`chadmsi` and `desktop-ecrkhb0` on it), and Funnel publishes port 8001 as
`https://estimating.<tailnet>.ts.net/` with a Let's Encrypt certificate.
tailscaled holds an outbound connection to Tailscale's relays, so no inbound
port is opened anywhere, and TLS terminates on the box, so the relay never
sees the traffic in clear. Chad: "sure...".

The steps are in `fedora-migration-runbook.md` under "Public access". The
install and the sign-in are root's, so Chad's; the funnel command and the
verification are the ops side's.

## Live

`https://estimating.tail5fb2cd.ts.net/` since 2026-09-09 ~12:05 PM. Verified
from outside the tailnet (the laptop, forced through the public ingress at
`199.38.181.54`): the health check answers in under half a second, the
page is served, the API is a 401 without a session, a wrong-password
sign-in reaches the log from the laptop's public address (so
`X-Forwarded-For` is honoured on the real path, not only in the loopback
test), and the certificate is Let's Encrypt's, good to 2026-12-08 and
renewed by Tailscale. The LAN address and its private CA stay as they were.

## What is public then

Everything the port serves: the sign-in page, the static assets, `/health`,
and the API behind its session cookie. Two things about that were fine on a
LAN and not on the internet, and both changed in the same commit (sql/083).

### The login box was a free guess

Nothing counted a wrong password. Each try cost the server ~150 ms of scrypt
and the guesser nothing, forever. Now:

* Every failed sign-in is a `login_failures` row: the name as typed
  (lowercased and trimmed, real or not) and the address it came from.
* Five failures for one name inside fifteen minutes lock that name until
  fifteen minutes after the fifth. Twenty from one address lock the address
  the same way. Five is a person mistyping; twenty is a script.
* A locked try is refused with a 429 and a `Retry-After` header before the
  password is looked at, so it neither costs the scrypt nor counts as another
  failure, and the right password does not get in either. The message says
  which ("for that username" or "from this address") and how long, and the
  sign-in box shows it as it shows the 401.
* A sign-in that succeeds clears the name's rows. Rows older than a day go
  with the next failure's housekeeping.
* A name nobody has locks the same as a real one, so the lockout says nothing
  about which names exist, as the 401 already did not.

The address is `request.client.host`. Through Funnel the connection reaches
uvicorn from 127.0.0.1 carrying `X-Forwarded-For`, which uvicorn trusts from
loopback by default (`--forwarded-allow-ips` is `127.0.0.1`), so the lockout
and the audit log see the phone's address, not tailscaled's.

### The API documented itself to anyone

`/docs`, `/redoc` and `/openapi.json` listed every route and schema to
whoever could reach the port. They are still there, for the signed-in only:
FastAPI's automatic routes are off and the same three pages are served by
routes that depend on `current_user`, a 401 without a session like the rest.

### What was already right

The session cookie is HttpOnly, SameSite=Lax and Secure whenever the scheme
is https, which it is on the LAN and through Funnel both. Passwords are
scrypt at 2**15 with a per-user salt. CORS is off; the SPA is same-origin.
The roles gate every write (`app/policy.py`). Sessions end after twelve idle
hours or thirty days.

## Tests

`backend/tests/test_auth.py`: four wrong tries and then the right password
signs in and clears the count; five lock the name, the right password is a
429 with the exact message and a `Retry-After` inside fifteen minutes, the
refused try is not counted, and fifteen minutes on the right password signs
in and the count is zero; a name nobody has locks the same; twenty failures
from one address under twenty different names lock the address; a failure a
day old goes with the next one; `/docs`, `/redoc` and `/openapi.json` are a
401 without a session and served with one, the schema carrying the routes.

## Not done here

* The daily report form itself, and the `foreman` role it needs (its own
  spec, after the Jotform import).
* A rate limit on the API beyond sign-in; every other route already needs a
  session.
* Telling the foremen the address: nothing to tell until the daily report
  form exists; the office keeps using the LAN address.
