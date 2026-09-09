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

## Still to do on the box

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
