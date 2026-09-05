"""
The database refuses a markup or a waste factor outside its range (sql/057).

sql/020 put these bounds on `estimates` with the reasoning that a waste
factor of 5 is 500%, and a number like that is far more likely a slipped
decimal than a decision. sql/033 created `estimate_sections` with the same
seven columns and no CHECK on any of them; sql/034 then dropped the checked
originals. The invariant was lost in the move and nothing noticed for a week,
because the API bounds the same fields (schemas/estimate_section.py) and the
screen is the only writer anybody exercised.

psql, a script, a job rule and backend/debug_section.py are writers too. The
database is the one place every one of them passes through, so that is where
the range lives — and this file is what says so.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

OUT_OF_RANGE = [
    ("margin_pct", "2.5"),
    ("margin_pct", "-0.1"),
    ("contingency_pct", "3"),
    ("form_percent", "2.5"),
    ("waste_concrete", "1.5"),
    ("waste_sand", "-0.01"),
    ("waste_rebar", "5"),
]

IN_RANGE = [
    ("margin_pct", "2"),
    ("margin_pct", "0"),
    ("contingency_pct", "0.03"),
    ("form_percent", None),
    ("form_percent", "2"),
    ("waste_concrete", "1"),
    ("waste_sand", None),
    ("waste_rebar", "0"),
]


def _set(db, section_id, column, value):
    db.execute(
        text(f"UPDATE estimate_sections SET {column} = :v WHERE id = :i"),
        {"v": None if value is None else Decimal(value), "i": str(section_id)},
    )


@pytest.mark.parametrize("column,value", OUT_OF_RANGE, ids=[f"{c}={v}" for c, v in OUT_OF_RANGE])
def test_the_database_refuses_a_figure_outside_its_range(db, section, column, value):
    """Straight SQL, past the API. The constraint is the only thing in the way."""
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _set(db, section.id, column, value)
    # ...and the refusal did not take the session down with it.
    assert db.execute(text("SELECT 1")).scalar() == 1


@pytest.mark.parametrize("column,value", IN_RANGE, ids=[f"{c}={v}" for c, v in IN_RANGE])
def test_the_edges_and_null_are_allowed(db, section, column, value):
    """
    0 and the top of each range are real values; NULL on form % and the
    wastes means "inherit the ladder" and must stay writable.
    """
    with db.begin_nested():
        _set(db, section.id, column, value)
    stored = db.execute(
        text(f"SELECT {column} FROM estimate_sections WHERE id = :i"),
        {"i": str(section.id)},
    ).scalar()
    assert (stored is None) == (value is None)
    if value is not None:
        assert Decimal(str(stored)) == Decimal(value)


def test_the_seven_constraints_are_on_the_table(db):
    """By name, so a migration that drops one to 'tidy up' fails here."""
    names = set(
        db.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'estimate_sections'::regclass AND contype = 'c'"
            )
        ).scalars()
    )
    for col in (
        "margin_pct", "contingency_pct", "form_percent",
        "waste_concrete", "waste_sand", "waste_rebar",
    ):
        assert f"estimate_sections_{col}_check" in names, col
