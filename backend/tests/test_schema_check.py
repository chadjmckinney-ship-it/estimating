"""
The startup schema guard (app/schema_check.py).

Written after the second time the app was started against a database missing a
migration. Both times it surfaced as a 500 with a psycopg2 UndefinedColumn
buried in a stack trace, minutes after boot, on whichever endpoint happened to
touch the new column — and once it read to Chad as "the site has reverted to
phase 1".

The information needed to fix it in ten seconds was available at startup.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app import schema_check


def test_a_current_database_is_clean(engine):
    """The normal case: sql/ and schema_migrations agree, boot proceeds."""
    assert schema_check.pending(engine) == []


def test_an_untracked_database_is_left_alone(engine, monkeypatch):
    """
    A database with no schema_migrations table cannot be judged. Refusing there
    would strand anyone whose database predates apply_sql.py, and we genuinely
    do not know whether it is behind.
    """
    monkeypatch.setattr(schema_check, "applied_migrations", lambda _e: None)
    assert schema_check.pending(engine) == []
    schema_check.check(engine)  # does not raise


def test_an_empty_tracking_table_is_left_alone(engine, monkeypatch):
    """Same reasoning: recorded nothing is not the same as ran nothing."""
    monkeypatch.setattr(schema_check, "applied_migrations", lambda _e: set())
    schema_check.check(engine)


def test_a_missing_migration_is_named(engine, monkeypatch):
    """
    The failure that matters. The message has to carry the filename and the
    command, because the person reading it is mid-task and the last two times
    they got a stack trace instead.
    """
    done = schema_check.applied_migrations(engine)
    assert done, "the test database should be tracking migrations"
    newest = sorted(schema_check.migration_files())[-1]
    monkeypatch.setattr(
        schema_check, "applied_migrations", lambda _e: done - {newest}
    )

    assert schema_check.pending(engine) == [newest]
    with pytest.raises(schema_check.PendingMigrations) as err:
        schema_check.check(engine)

    msg = str(err.value)
    assert newest in msg
    assert "apply_sql.py --all" in msg


def test_several_missing_migrations_are_all_listed(engine, monkeypatch):
    done = schema_check.applied_migrations(engine)
    last_two = sorted(schema_check.migration_files())[-2:]
    monkeypatch.setattr(
        schema_check, "applied_migrations", lambda _e: done - set(last_two)
    )
    with pytest.raises(schema_check.PendingMigrations) as err:
        schema_check.check(engine)
    for name in last_two:
        assert name in str(err.value)


def test_the_override_lets_you_start_anyway(engine, monkeypatch):
    """
    Being unable to start at all is its own failure mode — inspecting a database
    you are part-way through repairing, for instance. The variable is named so
    it cannot be set by accident.
    """
    done = schema_check.applied_migrations(engine)
    newest = sorted(schema_check.migration_files())[-1]
    monkeypatch.setattr(schema_check, "applied_migrations", lambda _e: done - {newest})
    monkeypatch.setenv(schema_check.OVERRIDE_ENV, "1")
    schema_check.check(engine)  # does not raise


def test_the_test_database_records_what_it_ran(engine):
    """
    dbsetup builds the test database by running sql/ straight through rather
    than via apply_sql.py. It now records what it ran, so this guard is
    exercised by the endpoint tests instead of being switched off in the one
    place it should be tested.
    """
    with engine.connect() as conn:
        recorded = set(
            conn.execute(text("SELECT filename FROM schema_migrations")).scalars().all()
        )
    assert set(schema_check.migration_files()) <= recorded
