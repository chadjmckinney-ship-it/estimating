"""
The migration runner (backend/apply_sql.py) — the script that changes the live
database — had no test of its own (audit 2026-09-04, P3 — batch 4, 2026-09-06).

What it promises: one file, one transaction, recorded only on success; a file
already recorded is skipped, not re-run; the files run in filename order, both
`015_` files included. Everything here runs against the TEST database (the
`_test` suffix guard in tests/dbsetup.py) and cleans up after itself.
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy import text

import apply_sql

TABLE = "zz_apply_sql_test"


@pytest.fixture
def clean(engine):
    """Drop the scratch table and forget the scratch files, before and after."""

    def _clean():
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
            conn.execute(text("DELETE FROM schema_migrations WHERE filename LIKE 'zz_%'"))

    _clean()
    yield
    _clean()


def _exists(engine, table: str) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar())


def _recorded(engine, name: str) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(
            text("SELECT 1 FROM schema_migrations WHERE filename = :f"), {"f": name}
        ).scalar())


def test_a_file_applies_whole_and_is_recorded(engine, tmp_path, clean):
    path = tmp_path / "zz_one.sql"
    path.write_text(f"CREATE TABLE {TABLE} (id int);\nINSERT INTO {TABLE} VALUES (1), (2);\n", encoding="utf-8")
    apply_sql.apply_one(engine, path)
    assert _exists(engine, TABLE)
    with engine.connect() as conn:
        assert conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 2
    assert _recorded(engine, "zz_one.sql")


def test_a_failing_file_rolls_back_and_records_nothing(engine, tmp_path, clean):
    path = tmp_path / "zz_bad.sql"
    path.write_text(f"CREATE TABLE {TABLE} (id int);\nSELECT 1/0;\n", encoding="utf-8")
    with pytest.raises(Exception):
        apply_sql.apply_one(engine, path)
    assert not _exists(engine, TABLE), "the CREATE before the failure must roll back with it"
    assert not _recorded(engine, "zz_bad.sql")


def test_main_runs_a_file_once_and_skips_it_after(engine, tmp_path, clean, monkeypatch, capsys):
    monkeypatch.setattr(apply_sql, "engine", lambda: engine)
    path = tmp_path / "zz_main.sql"
    path.write_text(f"CREATE TABLE {TABLE} (id int);\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["apply_sql.py", str(path), "--no-backup"])
    assert apply_sql.main() == 0
    assert _exists(engine, TABLE) and _recorded(engine, "zz_main.sql")
    assert "applied  zz_main.sql" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["apply_sql.py", str(path), "--no-backup"])
    assert apply_sql.main() == 0
    out = capsys.readouterr().out
    assert "skipped  zz_main.sql (already applied)" in out and "nothing to do" in out


def test_mark_applied_records_without_running(engine, tmp_path, clean, monkeypatch):
    monkeypatch.setattr(apply_sql, "engine", lambda: engine)
    path = tmp_path / "zz_marked.sql"
    path.write_text(f"CREATE TABLE {TABLE} (id int);\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["apply_sql.py", "--mark-applied", str(path)])
    assert apply_sql.main() == 0
    assert _recorded(engine, "zz_marked.sql")
    assert not _exists(engine, TABLE)


def test_a_missing_file_is_refused_before_anything_runs(engine, tmp_path, clean, monkeypatch, capsys):
    monkeypatch.setattr(apply_sql, "engine", lambda: engine)
    monkeypatch.setattr(sys, "argv", ["apply_sql.py", str(tmp_path / "zz_nope.sql"), "--no-backup"])
    assert apply_sql.main() == 2
    assert "not found" in capsys.readouterr().err


def test_status_lists_every_file_and_what_ran(engine, monkeypatch, capsys):
    monkeypatch.setattr(apply_sql, "engine", lambda: engine)
    monkeypatch.setattr(sys, "argv", ["apply_sql.py", "--status"])
    assert apply_sql.main() == 0
    out = capsys.readouterr().out
    for p in apply_sql.all_migrations():
        assert p.name in out
    assert "[x] 001_" in out  # the test database is built from sql/, and says so


def test_the_files_run_in_filename_order_with_both_015s():
    names = [p.name for p in apply_sql.all_migrations()]
    assert names == sorted(names)
    assert sum(n.startswith("015_") for n in names) == 2
    assert names[-1] >= "067_"
