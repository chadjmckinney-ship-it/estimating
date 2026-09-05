"""
A footing's top and bottom mats can differ (sql/059).

Chad, 2026-09-05, ~5:20 AM, looking at the wall grid freshly split into a wall
line and a footing line: "there are times with footings when the top and
bottom mat are different."

Until then the footing carried one bar set and a mat count that multiplied it
— the workbook's shape, right for LBJ (#5 @ 12" top and bottom on all sixteen
rows) and wrong for a footing with #5 @ 12" on the bottom and #4 @ 18" on top.
Now each mat is its own (spacing, size): a mat with no spacing or no size
contributes nothing, a one-mat footing leaves the top blank, and the footing's
steel is the sum of its mats. Per mat nothing changed — both directions, E*N/P
each, the "added twice" the module docstring defends — so two identical mats
come to exactly what "2 mats" came to and the reconciled 33,727.83 lb stands
(test_walls.py checks that number, not this file).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import walls as wl
from tests import walls_fixture as wf

D = Decimal


def mat(length_ft, width_in, spacing_in, size) -> Decimal:
    """One mat by hand, the sheet's weights: E * (N/P) * lb/ft, both directions."""
    return D(length_ft) * (D(width_in) / D(spacing_in)) * wl.sheet_bar_lb_per_ft(size) * 2


# ---------------------------------------------------------------- formula ----


def test_two_identical_mats_are_what_two_mats_were():
    """LBJ's first row: 135 ft on a 70" footing, #5 @ 12" top and bottom."""
    assert wl.footing_rebar_lb(None, 135, 70, 12, 5, 12, 5, sheet=True) == mat(135, 70, 12, 5) * 2


def test_mats_that_differ_are_each_their_own():
    got = wl.footing_rebar_lb(None, 135, 70, 12, 5, 18, 4, sheet=True)
    assert got == mat(135, 70, 12, 5) + mat(135, 70, 18, 4)
    assert got < mat(135, 70, 12, 5) * 2  # a lighter top mat is less steel, not "2 mats"


def test_a_one_mat_footing_leaves_the_top_blank():
    assert wl.footing_rebar_lb(None, 135, 70, 12, 5, None, None, sheet=True) == mat(135, 70, 12, 5)


def test_a_mat_missing_its_spacing_or_its_size_is_no_mat():
    # bottom has no size, top has no spacing: nothing, not a zero-weight bar
    assert wl.footing_rebar_lb(None, 135, 70, 12, None, None, 5, sheet=True) == 0
    # a spacing of 0 is no mat either — never a divide by zero
    assert wl.footing_rebar_lb(None, 135, 70, 0, 5, 18, None, sheet=True) == 0


# -------------------------------------------------------------------- API ----


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_the_grid_saves_a_footing_whose_mats_differ(client, db, estimate):
    section = wf.build(db, estimate)
    r = client.put("/api/wall-runs/bulk", json={
        "section_id": str(section.id),
        "rows": [{
            "label": "W-two", "length_ft": 100, "wall_thick_in": 12, "wall_height_in": 48,
            "ftg_width_in": 36, "ftg_thick_in": 12,
            "ftg_bot_spacing_in": 12, "ftg_bot_size": 5,
            "ftg_top_spacing_in": 18, "ftg_top_size": 4,
        }],
    })
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["label"] == "W-two")
    assert row["ftg_bot_size"] == 5 and D(row["ftg_bot_spacing_in"]) == 12
    assert row["ftg_top_size"] == 4 and D(row["ftg_top_spacing_in"]) == 18
    # Stored steel is the two mats at the catalog's bar weights, plus the
    # section's 10% rebar waste, to the thousandth — the same arithmetic the
    # refresh does, so a change to either side of it shows here.
    bare = wl.footing_mat_lb(db, 100, 36, 12, 5) + wl.footing_mat_lb(db, 100, 36, 18, 4)
    assert D(row["calc_footing_rebar_lb"]) == (bare * D("1.10")).quantize(D("0.001"))
    assert bare > 0


def test_a_one_mat_footing_saves_with_the_top_blank(client, db, estimate):
    section = wf.build(db, estimate)
    r = client.put("/api/wall-runs/bulk", json={
        "section_id": str(section.id),
        "rows": [{
            "label": "W-one", "length_ft": 100, "wall_height_in": 48,
            "ftg_width_in": 24, "ftg_thick_in": 12,
            "ftg_bot_spacing_in": 12, "ftg_bot_size": 5,
            "ftg_top_spacing_in": None, "ftg_top_size": None,
        }],
    })
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["label"] == "W-one")
    assert row["ftg_top_size"] is None and row["ftg_top_spacing_in"] is None
    bare = wl.footing_mat_lb(db, 100, 24, 12, 5)
    assert D(row["calc_footing_rebar_lb"]) == (bare * D("1.10")).quantize(D("0.001"))


def test_the_old_field_names_are_refused_by_name(client, db, estimate):
    """The pre-059 shape — one set and a count — is a 422 naming each field."""
    section = wf.build(db, estimate)
    r = client.put("/api/wall-runs/bulk", json={
        "section_id": str(section.id),
        "rows": [{"length_ft": 10, "wall_height_in": 36,
                  "ftg_spacing_in": 12, "ftg_size": 5, "ftg_mats": 2}],
    })
    assert r.status_code == 422, r.text
    assert {d["loc"][-1] for d in r.json()["detail"]} == {"ftg_spacing_in", "ftg_size", "ftg_mats"}
