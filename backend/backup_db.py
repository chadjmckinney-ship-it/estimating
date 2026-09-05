"""
Back up the estimating database with pg_dump, and prove the dump can be read.

    python backend/backup_db.py                       # dump to ~/Backups/estimating
    python backend/backup_db.py --label pre-059       # name the moment
    python backend/backup_db.py --copy-to "C:/Users/Chad/OneDrive - S and S Concrete Contractors Inc/Backups"
    python backend/backup_db.py --list                # what is there
    python backend/backup_db.py --restore-help        # how to get one back

Chad, 2026-09-05: "lets do the pg_dump backups." Until today the only dump
the database had ever had was the one taken by hand before sql/059, and
docs/notes.md had carried "No backup job on the laptop DB" since July.

What it does, every time:

  1. pg_dump -Fc (custom format: compressed, restorable table-by-table) of
     the app's DATABASE_URL — the same one apply_sql.py and the API use, so
     it works wherever they work — into estimating-YYYYMMDD-HHMMSS[-label].dump.
  2. pg_restore --list on the file it just wrote. A dump nobody has ever
     tried to read is not a backup; this reads the table of contents and
     refuses to report success unless schema_migrations is in it.
  3. Optionally copies the file somewhere else (--copy-to), for a second
     disk — OneDrive is the obvious one on this machine.
  4. Prunes: keeps the newest --keep dumps (30 by default) in the dump
     directory and deletes the rest. Only files this script named are
     touched; a copy-to directory is never pruned.

apply_sql.py calls backup() before it applies anything, so a migration can
always be undone by the dump taken the minute before it ran.

Restore (see --restore-help): pg_restore into a NEW database first, look,
then swap — never straight over the live one.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402

DEFAULT_DIR = Path.home() / "Backups" / "estimating"
PATTERN = re.compile(r"^estimating-\d{8}-\d{6}(-[A-Za-z0-9_.-]+)?\.dump$")


def libpq_url(url: str | None = None) -> str:
    """The app's SQLAlchemy URL as libpq wants it: no '+driver'."""
    u = url or settings.database_url
    return re.sub(r"^postgresql\+[a-z0-9]+://", "postgresql://", u)


def db_name(url: str | None = None) -> str:
    return libpq_url(url).rsplit("/", 1)[-1].split("?")[0] or "estimating"


def pg_bin(tool: str) -> Path:
    """pg_dump / pg_restore: PG_BIN, then PATH, then the usual Windows homes."""
    env = os.environ.get("PG_BIN")
    candidates = []
    if env:
        candidates.append(Path(env) / f"{tool}.exe")
        candidates.append(Path(env) / tool)
    found = shutil.which(tool)
    if found:
        candidates.append(Path(found))
    for v in ("17", "16", "15"):
        candidates.append(Path(rf"C:\Program Files\PostgreSQL\{v}\bin\{tool}.exe"))
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        f"{tool} not found. Set PG_BIN to the PostgreSQL bin directory "
        r"(e.g. C:\Program Files\PostgreSQL\17\bin) or put it on PATH."
    )


def verify(dump: Path) -> int:
    """pg_restore --list: the table of contents. Returns the entry count."""
    out = subprocess.run(
        [str(pg_bin("pg_restore")), "--list", str(dump)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"pg_restore --list failed on {dump.name}:\n{out.stderr.strip()}")
    entries = [ln for ln in out.stdout.splitlines() if ln and not ln.startswith(";")]
    if not any("schema_migrations" in ln for ln in entries):
        raise RuntimeError(f"{dump.name} lists no schema_migrations table — not a dump of this app")
    return len(entries)


def prune(dest: Path, keep: int) -> list[Path]:
    """Keep the newest `keep` dumps this script named; return what was removed."""
    # Newest by the file's own time, not by name: "…-165050-2.dump" sorts
    # before "…-165050.dump" as text and is the newer of the two.
    dumps = sorted(
        (p for p in dest.iterdir() if PATTERN.match(p.name)),
        key=lambda p: (p.stat().st_mtime, p.name),
    )
    removed = []
    for p in dumps[:-keep] if keep > 0 else []:
        p.unlink()
        removed.append(p)
    return removed


def backup(
    dest: Path | None = None,
    *,
    url: str | None = None,
    keep: int = 30,
    label: str | None = None,
    copy_to: Path | None = None,
    quiet: bool = False,
) -> Path:
    dest = Path(dest or DEFAULT_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-{re.sub(r'[^A-Za-z0-9_.-]+', '-', label)}" if label else ""
    base = f"estimating-{stamp}{suffix}"
    copy_dir = Path(copy_to) if copy_to else None
    taken = lambda name: (dest / name).exists() or (copy_dir is not None and (copy_dir / name).exists())  # noqa: E731
    out = dest / f"{base}.dump"
    n = 1
    while taken(out.name):
        # Two dumps inside one second (a test, a nervous operator) must not
        # overwrite each other — here or in the copy directory: the second
        # one is "-2".
        n += 1
        out = dest / f"{base}-{n}.dump"

    cmd = [str(pg_bin("pg_dump")), "--dbname", libpq_url(url), "-Fc", "-f", str(out)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0:
        if out.exists():
            out.unlink()
        raise RuntimeError(f"pg_dump failed:\n{run.stderr.strip()}")

    entries = verify(out)
    size = out.stat().st_size
    if not quiet:
        print(f"  dumped   {db_name(url)} -> {out}  ({size / 1024:,.0f} KB, {entries} entries, verified)")

    if copy_dir is not None:
        copy_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, copy_dir / out.name)
        if not quiet:
            print(f"  copied   -> {copy_dir / out.name}")

    for p in prune(dest, keep):
        if not quiet:
            print(f"  pruned   {p.name}")
    return out


RESTORE_HELP = r"""
Restore — into a NEW database first, look, then swap. Never straight over
the live one.

  # 1. a fresh database to restore into
  psql -d postgres -c "CREATE DATABASE estimating_restored OWNER chad;"

  # 2. the dump into it (-Fc dumps need pg_restore, not psql)
  "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --dbname postgresql:///estimating_restored --no-owner "%USERPROFILE%\Backups\estimating\estimating-YYYYMMDD-HHMMSS.dump"

  # 3. look before you swap
  psql -d estimating_restored -c "SELECT count(*) FROM estimates; SELECT max(filename) FROM schema_migrations;"

  # 4. swap (stop the API first — it holds connections)
  psql -d postgres -c "ALTER DATABASE estimating RENAME TO estimating_broken;"
  psql -d postgres -c "ALTER DATABASE estimating_restored RENAME TO estimating;"

One table only (a wall_runs gone wrong, say):
  pg_restore --dbname postgresql:///estimating --data-only --table wall_runs --clean <dump>
""".strip("\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help=f"where dumps go (default {DEFAULT_DIR})")
    ap.add_argument("--keep", type=int, default=30, help="how many dumps to keep in --dir (default 30)")
    ap.add_argument("--label", help="a word for the file name, e.g. pre-059")
    ap.add_argument("--copy-to", type=Path, help="also copy the dump here (never pruned)")
    ap.add_argument("--list", action="store_true", help="list the dumps in --dir")
    ap.add_argument("--restore-help", action="store_true", help="how to restore one")
    args = ap.parse_args()

    if args.restore_help:
        print(RESTORE_HELP)
        return 0
    if args.list:
        dumps = sorted(p for p in args.dir.glob("*.dump") if PATTERN.match(p.name)) if args.dir.is_dir() else []
        if not dumps:
            print(f"no dumps in {args.dir}")
        for p in dumps:
            print(f"  {p.name:48s} {p.stat().st_size / 1024:8,.0f} KB")
        return 0

    print(f"database: {libpq_url()}", file=sys.stderr)
    try:
        backup(args.dir, keep=args.keep, label=args.label, copy_to=args.copy_to)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"\nBACKUP FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
