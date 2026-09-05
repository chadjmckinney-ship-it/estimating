"""
A blank cell on a grid is a zero, not a type error.

Chad, 2026-09-05, about 4 AM: "on walls and footings, if there is no
footings, i have to put a '0' in every footing field."

Why: the grid sends an empty cell as `null`, and the quantity fields on the
wall, deck and column schemas were plain decimals with a default of 0. A
default only applies when the key is ABSENT; an explicit null was a 422 —
"Decimal input should be an integer, float, string or Decimal object" — with
no field named in the toast. So a wall with no footing needed a 0 in five
boxes, a deck level with no mesh, stud rails or carton forms needed three,
and a column type needed its dimensions typed even when the row was only a
label. The same live database carried a wall run with five hand-typed zeros.

The rule now, on every quantity that is NOT NULL in its table: blank means
none. The bulk routes still refuse a new row with no length, no area or no
height — a blank that mattered is still caught, by name — and api.js names
the cell on any 422 (frontend/tests/api-errors.test.mjs).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests import columns_fixture as cf
from tests import deck_fixture as df
from tests import walls_fixture as wf

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ walls ----


def test_a_wall_with_no_footing_needs_no_zeros(client, db, estimate):
    section = wf.build(db, estimate)
    r = client.put("/api/wall-runs/bulk", json={
        "section_id": str(section.id),
        "rows": [{
            "label": "W-none", "length_ft": 50, "wall_thick_in": 12, "wall_height_in": 60,
            "backfill": False, "mix_design_id": None,
            "horiz_spacing_in": 12, "horiz_size": 5, "horiz_mats": 2,
            "vert_spacing_in": 12, "vert_size": 5, "vert_mats": 2,
            # Every footing cell left blank — the row as the grid sends it.
            "ftg_width_in": None, "ftg_thick_in": None, "ftg_spacing_in": None,
            "ftg_size": None, "ftg_mats": None,
        }],
    })
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["label"] == "W-none")
    assert D(row["ftg_width_in"]) == 0 and D(row["ftg_thick_in"]) == 0
    # ...and it costs what a wall with no footing costs: the wall, and no footing.
    assert D(row["calc_footing_sf"]) == 0
    assert D(row["calc_footing_concrete_cy"]) == 0
    assert D(row["calc_footing_rebar_lb"]) == 0
    assert D(row["calc_footing_cost"]) == 0
    assert D(row["calc_excavate_cy"]) == 0
    assert D(row["calc_wall_concrete_cy"]) > 0
    assert D(row["calc_form_ff"]) == D("250")        # 50 ft x 60" / 12, one face


def test_a_blank_that_matters_is_still_refused_by_name(client, db, estimate):
    """Blank means zero, and a new wall with zero length is not a wall."""
    section = wf.build(db, estimate)
    r = client.put("/api/wall-runs/bulk", json={
        "section_id": str(section.id),
        "rows": [{"label": "nothing", "length_ft": None, "wall_height_in": 36}],
    })
    assert r.status_code == 400, r.text
    assert "length" in r.json()["detail"]


def test_a_single_row_patch_takes_a_blank_footing_too(client, db, estimate):
    section = wf.build(db, estimate)
    rows = client.get(f"/api/wall-runs?section_id={section.id}").json()
    r = client.patch(f"/api/wall-runs/{rows[0]['id']}",
                     json={"ftg_width_in": None, "ftg_thick_in": None})
    assert r.status_code == 200, r.text
    assert D(r.json()["ftg_width_in"]) == 0
    assert D(r.json()["calc_footing_sf"]) == 0


# ------------------------------------------------------------------- deck ----


def test_a_deck_level_with_no_mesh_stud_rails_or_cartons_needs_no_zeros(client, db, estimate):
    section = df.build(db, estimate)
    r = client.put("/api/deck-levels/bulk", json={
        "section_id": str(section.id),
        "rows": [{
            "label": "level 4", "area_sf": 5000, "thickness_in": 14, "has_cable": True,
            "mix_design_id": None, "perm_edge_lf": None,
            "top_bar_size": 4, "top_bar_spacing_in": 10, "bot_bar_size": None,
            "bot_bar_spacing_in": None, "mesh_sf": None, "stud_rail_lb": None,
            "carton_form_sf": None,
        }],
    })
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["label"] == "level 4")
    for key in ("perm_edge_lf", "mesh_sf", "stud_rail_lb", "carton_form_sf"):
        assert D(row[key]) == 0, key
    assert D(row["calc_concrete_cy"]) > 0


def test_a_deck_level_with_no_area_is_still_refused(client, db, estimate):
    section = df.build(db, estimate)
    r = client.put("/api/deck-levels/bulk", json={
        "section_id": str(section.id),
        "rows": [{"label": "level 5", "area_sf": None, "thickness_in": 14}],
    })
    assert r.status_code == 400 and "area" in r.text


# ---------------------------------------------------------------- columns ----


def test_a_column_type_typed_a_cell_at_a_time_needs_no_zeros(client, db, estimate):
    """
    A schedule entry someone is still filling in: a label, a count and a
    height, the rest blank for now. It saves; a face count left blank is a
    wrapped column, not a 422.
    """
    section = cf.build(db, estimate)
    r = client.put("/api/column-types/bulk", json={
        "section_id": str(section.id),
        "rows": [{
            "label": "C5", "qty": 2, "height_ft": 10, "length_in": None, "width_in": None,
            "formed_faces": None, "mix_design_id": None,
            "vert1_count": None, "vert1_size": None, "vert2_count": None, "vert2_size": None,
            "vert3_count": None, "vert3_size": None, "tie_size": None, "tie_spacing_in": None,
            "dowel_count": None, "dowel_size": None, "dowel_length_ft": None,
        }],
    })
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["label"] == "C5")
    assert D(row["length_in"]) == 0 and D(row["width_in"]) == 0
    assert row["formed_faces"] == 4
    assert D(row["calc_form_sf"]) == 0


def test_a_column_type_with_no_height_is_still_refused(client, db, estimate):
    section = cf.build(db, estimate)
    r = client.put("/api/column-types/bulk", json={
        "section_id": str(section.id),
        "rows": [{"label": "C6", "qty": 2, "height_ft": None}],
    })
    assert r.status_code == 400, r.text
