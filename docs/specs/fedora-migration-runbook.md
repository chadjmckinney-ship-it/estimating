# Moving to the Fedora box — runbook

**Target:** Postgres, the API and a reverse proxy all on one headless Fedora
host, answering on a name, reachable by a few machines on the office LAN. The
Windows desktop becomes a browser.

**Status:** planned, not started. Written 2026-08-31.

---

## Settle these two first

### 1. Put the repo under version control

There is no `.git` in `Estimate_Projects`. Right now that costs nothing because
there is one copy on one machine. The moment there is a second copy on a server,
it costs a lot: no way to ask the box what it is running, no way to see what
changed between "working" and "not working", and no way to put it back.

This is the same shape as the migration problem `schema_migrations` solved. Do
it before the move, from the Windows box:

```
cd C:\Users\Chad\Estimate_Projects
git init
```

`.gitignore` — at minimum:

```
.venv*/
__pycache__/
*.pyc
.env
workbooks/
*.dump
```

`workbooks/` is excluded on purpose: those are client estimates, they are large,
and they are not source. Keep them backed up separately.

Then `git add -A && git commit -m "Phase 3 — paving"` and the server can pull
instead of being copied onto.

### 2. Decide what "a few machines on the LAN" means for safety

The app has **no authentication** and **no concurrency control**. Today that is
fine — one person, one machine, `127.0.0.1`. On a LAN it means:

- Anyone who reaches the URL can change catalog prices, recalculate, or delete
  an estimate. There is no login and no audit of who did it.
- Two people in the same section will overwrite each other with no warning. The
  paving grid is the sharpest case: a bulk save writes every row it was given,
  so whoever saves second wins and the first person's edits are gone with no
  error.
- One person hitting Recalculate reprices what another person is reading.

None of that blocks the move. Options, cheapest first:

| | What it buys | Cost |
|---|---|---|
| **Nothing, for now** | It is a small, trusted office and everyone knows who is in a job | Free. Fine while it is really one estimator at a time |
| **Basic auth at the proxy** | A shared password stops accidental access from a stray laptop; still no idea who did what | ~10 minutes in the proxy config |
| **A row-version check on save** | The grid refuses to overwrite a section someone else changed since you loaded it, and says so | A day. This is the one that actually protects work |
| **Real logins** | Who did what, per-user permissions | Well beyond this move |

My read: do the move, add basic auth at the proxy in the same sitting because it
is nearly free, and put the row-version check on the list for when a second
person genuinely starts estimating. Do not let it hold up the move.

---

## Before you leave Windows

### Check the Postgres versions match up

The restore target must be the **same major version or newer** than the source.
On Windows:

```
.\.venv-win\Scripts\python.exe backend\dbquery.py --sql "SELECT version()"
```

or `psql -c "select version()"`. Note the major number. Fedora 41 ships
PostgreSQL 16; Fedora 42 and 43 ship 17. If Windows is newer than what Fedora
packages, install the matching version from the PGDG repo rather than dumping
backwards — that direction does not work.

### Take the dump

Custom format, so the restore can be selective if something goes wrong:

```
pg_dump -Fc -d estimating -f estimating.dump
```

Take it **with the app stopped**, so nothing is mid-write.

Sanity-check it before you trust it:

```
pg_restore --list estimating.dump | find /c "TABLE DATA"
```

You should see a table-data entry for every table, `schema_migrations` among
them — that table is what tells the new box which of the 36 migrations it has.

### Write down what the old box holds

So the new one can be checked against it:

```
.\.venv-win\Scripts\python.exe backend\dbquery.py --check migrations
.\.venv-win\Scripts\python.exe backend\dbquery.py --check totals
```

Keep that output. It is the acceptance test for the restore.

---

## On the Fedora box

### Packages

```bash
sudo dnf install -y postgresql-server postgresql-contrib python3 python3-pip git
sudo dnf install -y caddy        # or nginx, see the proxy section
```

### Postgres

```bash
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

**Postgres should not listen on the network.** The API is on the same host now,
so leave `listen_addresses = 'localhost'` and let only the proxy be reachable.
That is one fewer thing exposed to the LAN for no loss of function.

Create the role and database:

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE estimating LOGIN PASSWORD 'put-a-real-one-here';
CREATE DATABASE estimating OWNER estimating;
SQL
```

Fedora defaults to `scram-sha-256`, which is what you want. Check
`/var/lib/pgsql/data/pg_hba.conf` has a `host ... 127.0.0.1/32 scram-sha-256`
line, then `sudo systemctl reload postgresql`.

### Restore

```bash
pg_restore -h 127.0.0.1 -U estimating -d estimating --no-owner estimating.dump
```

`--no-owner` because the Windows ownership does not exist here.

**Verify before going further:**

```bash
psql -h 127.0.0.1 -U estimating -d estimating -c \
  "SELECT count(*) FROM schema_migrations"           # expect 36
psql -h 127.0.0.1 -U estimating -d estimating -c \
  "SELECT name, calc_total_cost FROM estimates"      # match the Windows figures
```

If the counts and the money match what you wrote down, the data moved. If they
do not, stop here — everything after this assumes a good restore.

### The app

Run it as its own user with no login shell:

```bash
sudo useradd -r -s /usr/sbin/nologin -d /opt/estimating estimating
sudo -u estimating git clone <your repo> /opt/estimating/app
cd /opt/estimating/app
sudo -u estimating python3 -m venv .venv
sudo -u estimating .venv/bin/pip install -r backend/requirements.txt
```

The connection string goes in a file only that user can read — **not** in the
repo, and not in a `.gitignore`d file you might forget is there:

```bash
sudo install -o estimating -g estimating -m 0600 /dev/null /etc/estimating.env
sudo tee /etc/estimating.env >/dev/null <<'ENV'
DATABASE_URL=postgresql+psycopg2://estimating:put-a-real-one-here@127.0.0.1/estimating
ENV
```

`/etc/systemd/system/estimating.service`:

```ini
[Unit]
Description=S&S Estimating API
After=network-online.target postgresql.service
Wants=postgresql.service

[Service]
User=estimating
WorkingDirectory=/opt/estimating/app
EnvironmentFile=/etc/estimating.env
ExecStart=/opt/estimating/app/.venv/bin/uvicorn app.main:app \
          --app-dir backend --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=2
# It only ever needs to read its own tree and talk to a local socket.
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now estimating
journalctl -u estimating -f
```

Note `--host 127.0.0.1`: the API is reached through the proxy, not directly.
And note `--app-dir backend` — the same flag `run.ps1` exists to get right.
`app.main:app` with `backend.app.main:app` is the mistake that costs an hour.

### The proxy

Caddy, because on a LAN it is four lines and it will not fight you:

`/etc/caddy/Caddyfile`

```
http://estimating.lan {
    reverse_proxy 127.0.0.1:8001
}
```

```bash
sudo systemctl enable --now caddy
```

Plain HTTP is the honest choice here: a LAN name has no public DNS, so real TLS
means running an internal CA and trusting it on every machine. If you want TLS
later, `caddy` can issue its own — but browsers will warn until each machine
trusts that CA, which is a chore for a handful of desktops.

If you want the shared password now, that is the whole change:

```
http://estimating.lan {
    basicauth {
        chad <bcrypt-hash-from: caddy hash-password>
    }
    reverse_proxy 127.0.0.1:8001
}
```

`estimating.lan` needs to resolve. Either an A record on the office router's
DNS, or a `hosts` entry on each desktop pointing at the Fedora box's IP. The
router is less work in the long run.

### Firewall

Only the proxy is exposed. Postgres and uvicorn are both on localhost.

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

### SELinux

Fedora enforces it, and this is where a working setup looks broken. If you use
**nginx** instead of Caddy, nginx is not allowed to open a network connection to
your uvicorn port until you say so:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

Caddy runs unconfined on Fedora and does not need this. Either way, if something
returns 502 and the logs look fine, check `sudo ausearch -m avc -ts recent`
before you start rewriting config — the "check what is actually running" rule
applies to the kernel too.

### Backups

The whole point of a server is that it is not your desktop. Give it a timer.

`/etc/systemd/system/estimating-backup.service`

```ini
[Unit]
Description=Dump the estimating database

[Service]
Type=oneshot
User=postgres
ExecStart=/bin/bash -c '/usr/bin/pg_dump -Fc estimating \
  -f /var/backups/estimating/estimating-$(date +%%F).dump'
ExecStartPost=/bin/bash -c 'find /var/backups/estimating -name "*.dump" \
  -mtime +30 -delete'
```

`/etc/systemd/system/estimating-backup.timer`

```ini
[Unit]
Description=Nightly estimating dump

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo mkdir -p /var/backups/estimating
sudo chown postgres:postgres /var/backups/estimating
sudo systemctl enable --now estimating-backup.timer
```

**Then restore one.** A backup nobody has restored is a hope, not a backup.
Restore yesterday's into `estimating_restore_test` and count the estimates.

---

## Verification, in order

Do these in order and stop at the first failure. Each one rules out a layer, so
you never end up guessing which of five things is wrong.

| # | Check | Passes if |
|---|---|---|
| 1 | `systemctl status postgresql` | active |
| 2 | `psql -h 127.0.0.1 -U estimating -d estimating -c "select count(*) from schema_migrations"` | 36 |
| 3 | `systemctl status estimating` | active, no restarts in `journalctl -u estimating` |
| 4 | `curl -s localhost:8001/health` | `{"status":"ok",...}` |
| 5 | `curl -s localhost:8001/openapi.json \| grep -c mono-slabs/bulk` | 1 — proves it is phase-3 code |
| 6 | `curl -s http://estimating.lan/health` from **another desktop** | same JSON — proxy, DNS and firewall all good |
| 7 | Open the app, load the paving section | quantities match: 272,703 SF, 4,832.4125 CY, 9,537 curb LF |
| 8 | `apply_sql.py --status` from `/opt/estimating/app` | 36 of 36 |

Step 5 is the one worth keeping as a habit. Three separate evenings on this
project were lost to new code meeting an old something — a stale uvicorn, an
unapplied migration, a cached browser. One `grep` for a string you know is new
answers it before you read a line of code.

---

## Rollback

Nothing is destroyed by this. The Windows install stays exactly as it is until
you choose to stop using it — do not uninstall anything on that box until the
Fedora one has been the only one used for a week and a backup has been restored
from it successfully.

If the move goes wrong: point the browser back at `127.0.0.1:8001` on Windows.
That is the whole rollback.

The one real hazard is **both** running for a while against **different**
databases, and estimates being edited in each. Pick a switch-over moment, stop
the Windows service, and do not start it again.

---

## What changes for how we work

Once the app lives on Fedora, I can no longer reach it the way I reach the
Windows box — this session's bridge goes to your desktop. I can still see the
app through your Chrome, and you can paste `journalctl` output, but the "let me
just look" shortcut narrows. Git helps a lot here: if the repo is pushed
somewhere I can read, I can see what the server is running instead of asking.
