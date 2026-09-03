"""
Build a throwaway test database from sql/.

Nothing here will touch a database whose name does not end in `_test` — that
guard is the only thing standing between a test run and the live bids, so do
not relax it.

    python backend/tests/dbsetup.py            # rebuild estimating_test
    TEST_DATABASE_URL=... python backend/tests/dbsetup.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = REPO_ROOT / "sql"

DEFAULT_URL = "postgresql+psycopg2:///estimating_test"


def test_database_url() -> URL:
    """The URL tests run against, with the `_test` suffix enforced."""
    url = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_URL))
    name = url.database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database {name!r}: the test database "
            "name must end in '_test'. Set TEST_DATABASE_URL to something like "
            "postgresql+psycopg2:///estimating_test."
        )
    return url


def migration_files() -> list[Path]:
    """
    Every sql/*.sql in filename order.

    Filename order is the applied order — there is no migrations table. Note
    that two files share the 015 prefix (015_forming_materials, then
    015_poly_sides_only); they are independent, and this order is the one the
    live database was built with.
    """
    return sorted(p for p in SQL_DIR.glob("*.sql"))


def rebuild(url: URL | None = None, *, echo: bool = True) -> URL:
    """Drop, recreate and migrate the test database. Returns its URL."""
    url = url or test_database_url()
    name = url.database

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"
            ),
            {"n": name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()

    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        for path in migration_files():
            if echo:
                print(f"  {path.name}", file=sys.stderr)
            with raw.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
    engine.dispose()
    ensure_recorded(url)
    return url


def ensure_recorded(url: URL) -> None:
    """
    Record every sql/ file in schema_migrations.

    The test database is built by running the files straight through rather
    than via apply_sql.py, so nothing used to be recorded — which left the test
    database looking permanently un-migrated. That was harmless until the app
    started refusing to boot on pending migrations (app/schema_check.py); now
    it would either break every endpoint test or, worse, force the guard to be
    switched off in tests, which is the one place it should be exercised.
    """
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "filename text PRIMARY KEY, "
                    "applied_at timestamptz NOT NULL DEFAULT now(), "
                    "note text)"
                )
            )
            for path in migration_files():
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations (filename, note) "
                        "VALUES (:f, 'test rebuild') ON CONFLICT (filename) DO NOTHING"
                    ),
                    {"f": path.name},
                )
    finally:
        engine.dispose()


def is_migrated(url: URL) -> bool:
    """True if the calc helpers are present, i.e. the schema has been applied."""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT to_regproc('calc_concrete_cy')")).scalar() is not None
    except Exception:
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    target = test_database_url()
    print(f"Rebuilding {target.database} from {SQL_DIR}", file=sys.stderr)
    rebuild(target)
    print("done", file=sys.stderr)
