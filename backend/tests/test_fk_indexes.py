"""
Every foreign key that can be deleted through has an index (sql/067).

Audit 2026-09-04, P3 — batch 4, 2026-09-06. Sixteen foreign-key columns had
none; a DELETE of the referenced row scanned the whole table for each one.
The one deliberate exception is the bar-size columns pointing at bar_weights
(sql/066): nothing deletes a bar size, the column holds one of a dozen
values, and an index there is dead weight on every write. This test names
that exception and refuses any other.
"""

from __future__ import annotations

from sqlalchemy import text

UNINDEXED_FKS = """
SELECT c.conrelid::regclass::text AS tbl, a.attname AS col, c.confrelid::regclass::text AS ref
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = a.attnum
  )
ORDER BY 1, 2
"""


def test_every_fk_that_can_be_deleted_through_has_an_index(db):
    rows = db.execute(text(UNINDEXED_FKS)).all()
    bare = [(t, c, r) for t, c, r in rows if r != "bar_weights"]
    assert not bare, f"foreign keys without an index: {bare}"


def test_the_bar_size_exception_is_the_only_one(db):
    rows = db.execute(text(UNINDEXED_FKS)).all()
    assert rows, "the bar-size columns are meant to stay unindexed (sql/067)"
    assert {r for _, _, r in rows} == {"bar_weights"}
