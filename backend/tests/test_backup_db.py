"""
The backup is real: it dumps, it proves the dump reads, it prunes, it copies.

Chad, 2026-09-05: "lets do the pg_dump backups." Runs pg_dump against the
TEST database (never the live one) into a temp directory, so it exercises the
same code path apply_sql.py runs before every migration. Skips, rather than
fails, on a box with no pg_dump — the app can run without one; the backup
cannot.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import backup_db as bk
from tests.dbsetup import test_database_url

try:
    bk.pg_bin("pg_dump")
    bk.pg_bin("pg_restore")
except FileNotFoundError as exc:  # pragma: no cover — depends on the box
    pytest.skip(f"no pg tools here: {exc}", allow_module_level=True)

TEST_URL = test_database_url().render_as_string(hide_password=False)


def test_it_dumps_verifies_and_names_the_moment(tmp_path):
    out = bk.backup(tmp_path, url=TEST_URL, label="pre-059", keep=5, quiet=True)
    assert out.parent == tmp_path and out.suffix == ".dump"
    assert bk.PATTERN.match(out.name) and out.name.endswith("-pre-059.dump"), out.name
    assert out.stat().st_size > 10_000
    # The table of contents reads, and it is THIS app's schema.
    assert bk.verify(out) > 50


def test_a_label_is_made_safe_for_a_file_name(tmp_path):
    out = bk.backup(tmp_path, url=TEST_URL, label="pre 059/footing mats", keep=5, quiet=True)
    assert out.name.endswith("-pre-059-footing-mats.dump"), out.name


def test_it_keeps_the_newest_and_prunes_only_its_own(tmp_path):
    stranger = tmp_path / "keep-me.dump"
    stranger.write_bytes(b"not ours")
    made = [bk.backup(tmp_path, url=TEST_URL, keep=2, quiet=True) for _ in range(3)]
    left = sorted(p.name for p in tmp_path.glob("*.dump"))
    assert made[0].name not in left, "the oldest of three goes when keep=2"
    assert made[1].name in left and made[2].name in left
    assert "keep-me.dump" in left, "a file this script did not name is never touched"


def test_copy_to_puts_a_second_copy_elsewhere(tmp_path):
    here = tmp_path / "local"
    there = tmp_path / "onedrive"
    out = bk.backup(here, url=TEST_URL, keep=5, copy_to=there, quiet=True)
    twin = there / out.name
    assert twin.is_file() and twin.stat().st_size == out.stat().st_size
    # ...and the copy directory is never pruned, however many dumps come.
    for _ in range(3):
        bk.backup(here, url=TEST_URL, keep=1, copy_to=there, quiet=True)
    assert len(list(there.glob("*.dump"))) == 4
    assert len(list(here.glob("*.dump"))) == 1


def test_the_url_is_the_apps_without_the_driver():
    assert bk.libpq_url("postgresql+psycopg2:///estimating") == "postgresql:///estimating"
    assert bk.libpq_url("postgresql+psycopg://u:p@host/db") == "postgresql://u:p@host/db"
    assert bk.db_name("postgresql+psycopg2:///estimating_test") == "estimating_test"


def test_a_bad_database_fails_loudly_and_leaves_no_file(tmp_path):
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        bk.backup(tmp_path, url="postgresql:///no_such_database_here", keep=5, quiet=True)
    assert not list(tmp_path.glob("*.dump"))


def test_the_default_directory_is_the_users_backups_folder():
    assert bk.DEFAULT_DIR == Path(os.path.expanduser("~")) / "Backups" / "estimating"
