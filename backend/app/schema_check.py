"""
Refuse to start on an out-of-date database.

Twice now the app has been started against a database missing a migration, and
both times it surfaced the same way: a 500 on some request, minutes later, with
a psycopg2 UndefinedColumn buried in a stack trace. Once it read as "the site
has reverted to phase 1". The information needed to fix it in ten seconds —
"sql/038 has not been applied" — was available at startup and nobody asked.

`run.ps1` does check, and prints pending files in yellow. But the bare
`python -m uvicorn` fallback (the one that exists because the PowerShell
execution policy blocks scripts) skips it entirely, and that is the launcher
that was used. A check that only runs on one of two launch paths is a check you
cannot rely on, so this one lives in the app.

Deliberately a hard failure rather than a warning. A warning scrolls past; a
model that does not match its schema produces wrong numbers or 500s, and on an
estimating system a wrong number is worse than no server.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

# An escape hatch, because being unable to start at all is its own failure mode
# — inspecting a database you are mid-way through repairing, for instance.
# Named so it cannot be set by accident and reads badly in a startup script.
OVERRIDE_ENV = "ALLOW_PENDING_MIGRATIONS"


class PendingMigrations(RuntimeError):
    pass


def migration_files() -> list[str]:
    if not SQL_DIR.is_dir():
        return []
    return sorted(p.name for p in SQL_DIR.glob("*.sql"))


def applied_migrations(engine: Engine) -> set[str] | None:
    """
    What the database says has run. None when it is not tracking at all — a
    different situation from "nothing has run", and it gets a different message.
    """
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('public.schema_migrations')")
        ).scalar()
        if exists is None:
            return None
        rows = conn.execute(text("SELECT filename FROM schema_migrations")).scalars().all()
    return set(rows)


def pending(engine: Engine) -> list[str]:
    on_disk = migration_files()
    if not on_disk:
        return []
    done = applied_migrations(engine)
    if done is None or not done:
        # Untracked. Refusing here would strand anyone whose database predates
        # apply_sql.py, and we genuinely cannot tell whether it is current.
        return []
    return [name for name in on_disk if name not in done]


def check(engine: Engine) -> None:
    """Raise PendingMigrations if the schema is behind the sql/ directory."""
    if os.environ.get(OVERRIDE_ENV) == "1":
        return
    missing = pending(engine)
    if not missing:
        return
    listed = "\n".join(f"    {name}" for name in missing)
    raise PendingMigrations(
        f"\n\nThe database is missing {len(missing)} migration"
        f"{'' if len(missing) == 1 else 's'}:\n\n{listed}\n\n"
        "Apply them, then start again:\n\n"
        "    python backend/apply_sql.py --all\n\n"
        "(On Windows: .venv-win\\Scripts\\python.exe backend\\apply_sql.py --all)\n\n"
        "The app is refusing to start because a model that does not match its\n"
        "schema returns wrong numbers or 500s on whichever request touches the\n"
        f"missing column. Set {OVERRIDE_ENV}=1 to start anyway.\n"
    )


def check_url(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        check(engine)
    finally:
        engine.dispose()
