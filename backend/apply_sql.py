"""
Apply sql/ migrations, and remember which ones have been applied.

Uses the same DATABASE_URL the app uses, so it works wherever the app works —
no psql on PATH, no guessing at Windows authentication.

    python backend/apply_sql.py --status
    python backend/apply_sql.py sql/027_sales_tax_and_uplifts.sql
    python backend/apply_sql.py --all
    python backend/apply_sql.py --mark-applied sql/0*.sql

Each file runs in its own transaction: it applies whole or not at all. Applied
files are recorded in `schema_migrations`, which is what the backlog item about
migration discipline was asking for — nothing used to record what a given
database had had run against it.

Note the two files sharing the `015_` prefix. Order here is filename order,
which is the order the live database was built in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parent
REPO_ROOT = BACKEND.parent
SQL_DIR = REPO_ROOT / "sql"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402

_TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    note        text
)
"""


def engine():
    return create_engine(settings.database_url)


def all_migrations() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


def applied(conn) -> set[str]:
    conn.execute(text(_TRACKING))
    rows = conn.execute(text("SELECT filename FROM schema_migrations")).scalars().all()
    return set(rows)


def record(conn, name: str, note: str | None = None) -> None:
    conn.execute(
        text(
            "INSERT INTO schema_migrations (filename, note) VALUES (:f, :n) "
            "ON CONFLICT (filename) DO NOTHING"
        ),
        {"f": name, "n": note},
    )


def apply_one(eng, path: Path) -> None:
    """One file, one transaction. A failure rolls the whole file back."""
    sql = path.read_text(encoding="utf-8")
    with eng.begin() as conn:
        conn.execute(text(_TRACKING))
        raw = conn.connection.dbapi_connection
        with raw.cursor() as cur:
            cur.execute(sql)
        record(conn, path.name)
    print(f"  applied  {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", help="sql files to apply, in the order given")
    ap.add_argument("--all", action="store_true", help="apply every unapplied file")
    ap.add_argument(
        "--mark-applied",
        action="store_true",
        help="record the named files as applied WITHOUT running them "
        "(for a database that already has them)",
    )
    ap.add_argument("--status", action="store_true", help="what has and hasn't run")
    args = ap.parse_args()

    eng = engine()
    print(f"database: {settings.database_url}", file=sys.stderr)

    with eng.begin() as conn:
        done = applied(conn)

    if args.status:
        print(f"\n{len(done)} of {len(all_migrations())} recorded as applied\n")
        for p in all_migrations():
            print(f"  [{'x' if p.name in done else ' '}] {p.name}")
        if not done:
            print(
                "\nNothing is recorded yet. If this database is already built, "
                "backfill first:\n  python backend/apply_sql.py --mark-applied sql/*.sql"
            )
        return 0

    if args.all and args.mark_applied:
        # Backfilling a database that was built before this script existed.
        targets = all_migrations()
    elif args.all:
        targets = [p for p in all_migrations() if p.name not in done]
        if not done and targets:
            print(
                "Refusing --all: nothing is recorded as applied, so this would "
                "re-run every migration against a database that may already have "
                "them. Backfill with '--mark-applied --all' first, or name files "
                "explicitly.",
                file=sys.stderr,
            )
            return 2
    else:
        targets = [Path(f) for f in args.files]
        if not targets:
            ap.print_help()
            return 2
        targets = [p if p.is_absolute() else (REPO_ROOT / p) for p in targets]

    missing = [p for p in targets if not p.is_file()]
    if missing:
        for p in missing:
            print(f"not found: {p}", file=sys.stderr)
        return 2

    if args.mark_applied:
        with eng.begin() as conn:
            for p in targets:
                record(conn, p.name, note="marked applied, not run")
                print(f"  recorded {p.name}")
        return 0

    todo = [p for p in targets if p.name not in done]
    for p in targets:
        if p.name in done:
            print(f"  skipped  {p.name} (already applied)")
    if not todo:
        print("nothing to do")
        return 0

    for p in todo:
        try:
            apply_one(eng, p)
        except Exception as exc:  # noqa: BLE001
            print(f"\nFAILED on {p.name} — rolled back:\n  {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
