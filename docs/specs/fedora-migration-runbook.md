# The office Fedora box — the app's home (2026-09-09)

**Status:** the app runs on the box as of 2026-09-09. This is the record of
what was done and how it is looked after; the plan it replaced was written
2026-08-31, before sign-in, https, the migration ledger and git existed, and
wanted a reverse proxy the app no longer needs.

**Chad, 2026-09-09:** "think we are about to the point of moving this to the
headless fedora box in my office."

## The box

| | |
|---|---|
| Address | `192.168.0.145` on the office LAN, hostname `estimating` (set 2026-09-09) |
| OS | Fedora 44, 4 cores, 16 GB |
| Disks | root on the NVMe, 475 GB after Chad grew the volume from its 15 GB install size; `/shared`, 440 GB, the backup disk |
| PostgreSQL | 18.4, the distro's own, already running for the box's other jobs; `chad` is a superuser through peer auth on the socket |
| Python | 3.14, the distro's own |
| Access | SSH as `chad` with the key on Chad's laptop; `sudo` needs a password, so root steps are Chad's |
| Other jobs | the nightly rclone sync to Google Drive, the local SSD backup, the Jotform reports to Notion, the 8:05 bid-list email — see the vault's Fedora Ops Box note |

## What runs where

Everything is under `chad`, no root, because the box's user services start
at boot (`Linger=yes`) and PostgreSQL trusts the OS user on its socket.

| Piece | Where |
|---|---|
| The repo | `~/estimating/app`, a clone of `github.com/chadjmckinney-ship-it/estimating` |
| The venv | `~/estimating/app/.venv`, `backend/requirements.txt` |
| The database | `estimating` on the box's PostgreSQL 18, reached as `postgresql+psycopg2:///estimating` — the app's default, so there is no `.env` |
| The certificates | `~/estimating/app/certs/`, made by `backend/make_certs.py --name estimating --ip 192.168.0.145`; `ca.crt` is the one file each PC installs |
| The app | `~/.config/systemd/user/estimating.service`: uvicorn, `--app-dir backend`, https on `0.0.0.0:8001`, restarts on failure |
| The backups | `~/.config/systemd/user/estimating-backup.timer`, 6 PM daily, `backend/backup_db.py --dir /shared/Backups/estimating --keep 60` |
| The firewall | port 8001/tcp opened by Chad; PostgreSQL is not reached from the LAN by the app |

## What was done, in order

1. **Chad, as root:** `dnf install -y git`, `firewall-cmd --permanent
   --add-port=8001/tcp && firewall-cmd --reload`, `hostnamectl set-hostname
   estimating`. He had already grown the root volume.
2. **The dump.** `backend/backup_db.py` on the laptop (custom format,
   verified), copied to the box with `scp`.
3. **The database.** `createdb estimating`, then `pg_restore -O -x -d
   estimating` — no owner, no privileges, because the Windows role does not
   exist on the box. Zero errors.
4. **The acceptance.** Identical on both machines: 82 rows in
   `schema_migrations`; the testing estimate at $3,269,171.82 cost and
   $3,824,354.02 sale; 1 project, 1 estimate, 12 sections, 20 pours, 1
   proposal, 71 lines, 83 materials, 5 people.
5. **The app.** `git clone`, `python3 -m venv .venv`, `pip install -r
   backend/requirements.txt` — which turned up `openpyxl` missing from the
   file (the laptop's venv had it by accident); listed now. The certificates,
   the user service, `systemctl --user enable --now estimating`, and the
   boot check passed the ledger at 82.
6. **Reached from the laptop:** `curl -k https://192.168.0.145:8001/health`
   answers `{"status":"ok","db":"estimating"}` and the OpenAPI carries
   `/api/proposals`, which proves the code is this week's.
7. **The first backup** to `/shared/Backups/estimating`, and the timer.

## Using it

* Open `https://192.168.0.145:8001/` (or `https://estimating:8001/` once the
  name resolves on your PC — a line in `hosts` does it: `192.168.0.145
  estimating`). Sign in as before; the people and passwords came over with
  the database.
* Once per PC, in an elevated prompt, trust the box's CA so the browser stops
  warning: `certutil -addstore -f Root <path>\estimating-fedora-ca.crt`. The
  file is `certs/ca.crt` on the box; a copy was put in Chad's Downloads.
* **Two databases exist until the cutover.** Pick the moment, stop the
  Windows app (`run.ps1` simply is not started again), and edit only on the
  box from then on. Anything typed into the Windows copy after the dump is
  not on the box.

## Looking after it

```bash
systemctl --user status estimating          # is it up
journalctl --user -u estimating -n 50       # what it said
systemctl --user restart estimating         # after a git pull
systemctl --user list-timers | grep estimating
ls -la /shared/Backups/estimating           # the dumps
```

**Updating the code:** `cd ~/estimating/app && git pull`, apply any new
migration with `.venv/bin/python backend/apply_sql.py sql/NNN.sql` (it takes
its own dump first), then `systemctl --user restart estimating`. The boot
check refuses to start with a migration pending, the same as on Windows.

**Restoring a dump:** `backend/backup_db.py --restore-help` prints it; the
short form is `createdb estimating_restore_test && pg_restore -O -x -d
estimating_restore_test <file>`, then count the estimates. Do it once a
quarter so the backup stays a backup.

**The certificate** is good for 825 days from 2026-09-09; `make_certs.py
--renew` on the box makes a fresh one from the same CA, so the PCs need
nothing new.

## Public access: Tailscale Funnel (2026-09-09)

The field foremen will fill in the daily report from their phones, so the
app needs a public address. Port-forwarding was the first idea; the office
router is a Netgear Nighthawk whose admin password and security questions
nobody has, so the box joins Chad's tailnet instead and Tailscale Funnel
publishes port 8001 under a public https name with a real certificate. No
router change, no open inbound port: tailscaled holds an outbound
connection to Tailscale's relays and terminates TLS on the box itself.

`docs/specs/public-access-spec.md` has the reasoning and what the app
changed for it (sql/083). The steps on the box, the first three as root:

```bash
sudo dnf install -y tailscale                 # 1.98.8 is in Fedora's own updates repo
sudo systemctl enable --now tailscaled
sudo tailscale up --operator=chad             # prints a login link: open it, sign in with the company account
tailscale funnel --bg https+insecure://127.0.0.1:8001
tailscale funnel status                       # the public https://estimating.<tailnet>.ts.net/ address
```

`--operator=chad` lets the `chad` account run `tailscale serve` and
`funnel` without sudo from then on. The first `funnel` command prints a
link if Funnel is not yet allowed on the tailnet; the link adds the
`funnel` node attribute to the tailnet policy. HTTPS certificates must be
on for the tailnet too (DNS page of the admin console); the first request
fetches the Let's Encrypt certificate and takes a few seconds.
`https+insecure` is the app's own https on 8001 behind the box's private
CA, which tailscaled is told not to verify. The connection reaches uvicorn
from 127.0.0.1 carrying `X-Forwarded-For`, which uvicorn trusts from
loopback by default, so the lockout and the audit log see the real
address.

To take it down: `tailscale funnel --https=443 off`. The LAN address keeps
working either way.

**Live since 2026-09-09 ~12:05 PM: `https://estimating.tail5fb2cd.ts.net/`.**
Chad ran the install and the sign-in (the box is `100.95.128.97` on the
tailnet, beside `chadmsi` and `chadrog`), turned HTTPS certificates on, and
approved Funnel from the link the first `funnel` command printed. Checked
from the laptop through the public ingress (`--resolve` to `199.38.181.54`,
so not over the tailnet): `/health` 200 in under half a second, the page
served, the API a 401 without a session, a wrong-password sign-in logged
from the laptop's public address rather than 127.0.0.1, and the
certificate from Let's Encrypt, good to 2026-12-08 and renewed by Tailscale
itself. The very first request took about half a minute while the
certificate was issued; every one after was immediate. A phone on the
public name needs no CA of ours; the box's own CA is only for the LAN
address.

## Still to do on the box

* Funnel is up (above). `tailscale funnel status` shows it; it survives a
  reboot (the serve config is tailscaled's own).
* The 8:05 bid-list email (`~/gmail-bid-notion-sync/email_current_bids.py`)
  reads Notion. It should read the app's `projects` table on the same box
  once the bid list moves in.
* The bid-invite intake: a reader of the estimating mailbox writing straight
  into `projects`, with the message id as the dedupe key, replacing both the
  disabled Gmail sync and the grok.com task.
* A second copy of the dumps off the box (the CIFS share or Google Drive);
  today they live on `/shared` only.
* The Windows laptop keeps its own database and backup task until the
  cutover has held for a week.
