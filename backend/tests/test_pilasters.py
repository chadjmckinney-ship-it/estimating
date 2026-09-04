"""
Pilasters (sql/051).

A pilaster is a short column and is taken off on the column schedule, so it is
a second section of kind `columns` — Chad, 2026-08-31, in sql/041:

    "I dont use the pilaster section because it doesnt let me add enough info
     and I just use column sheet for it since it is basically a short column…
     so when we create columns we can just make 2 and call the second section
     pilasters."

Almost nothing needed building. Two things did:

  * `formed_faces` — a column is wrapped, a pilaster has a wall on one or two
    of its L faces. Chad, asked which: **"varies by job — make it an input."**
  * the haul-off line, switched on here and off on a columns section
    (test_audit_small_fixes).

`formed_faces` is not a plywood adjustment. `calc_form_sf` is ALSO the basis
this section allocates every shared cost by (sql/045), so the face count moves
four labor lines, the nails, and the section's share of supervision,
equipment and contract services. That is what most of this file is about.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db import get_db
from app.main import app
from app.models.column_type import ColumnType
from app.models.estimate import Estimate
from app.services import columns as cv
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.recalc import recalc_section
from tests import columns_fixture as cf


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate):
    section = cf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _types(db, section_id) -> list[ColumnType]:
    return list(
        db.scalars(
            select(ColumnType)
            .where(ColumnType.section_id == section_id)
            .order_by(ColumnType.sort_order)
        ).all()
    )


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


# --------------------------------------------------------- the geometry ----


def test_the_three_face_counts_are_the_three_ways_a_column_meets_a_wall():
    """18 along the wall, 24 out of it, 12 ft, one of them.

        4  wrapped          (18 + 24) x 2 = 84"
        3  on a built wall   18 + 24 x 2  = 66"   one L face is the wall
        2  monolithic          24 x 2     = 48"   both L faces are the wall's
    """
    L, W, H = Decimal("18"), Decimal("24"), Decimal("12")
    assert cv.formed_perimeter_in(L, W, 4) == Decimal("84")
    assert cv.formed_perimeter_in(L, W, 3) == Decimal("66")
    assert cv.formed_perimeter_in(L, W, 2) == Decimal("48")

    # ...and in SF, which is what everything downstream actually reads.
    assert cv.form_sf(H, L, W, 1, 4) == Decimal("84.0000")
    assert cv.form_sf(H, L, W, 1, 3) == Decimal("66.0000")
    assert cv.form_sf(H, L, W, 1, 2) == Decimal("48.0000")


def test_the_unformed_face_is_always_an_L_face():
    """
    The convention the grid and sql/051 both state: enter L along the wall.
    A square column cannot tell you whether it is honoured, so this uses one
    that is not square and asserts WHICH dimension survives.
    """
    L, W = Decimal("18"), Decimal("24")
    # Dropping one L face removes 18, not 24.
    assert cv.formed_perimeter_in(L, W, 4) - cv.formed_perimeter_in(L, W, 3) == L
    # Dropping the second removes the other 18 — the W faces always stay.
    assert cv.formed_perimeter_in(L, W, 3) - cv.formed_perimeter_in(L, W, 2) == L
    assert cv.formed_perimeter_in(L, W, 2) == W * 2


def test_a_face_against_a_wall_carries_no_chamfer():
    """Four exposed corners wrapped; two when anything is against a wall —
    that corner is a joint, not an edge."""
    assert cv.formed_corners(4) == 4
    assert cv.formed_corners(3) == 2
    assert cv.formed_corners(2) == 2
    assert cv.chamfer_lf(Decimal("12"), 10, 4) == Decimal("480.000")
    assert cv.chamfer_lf(Decimal("12"), 10, 3) == Decimal("240.000")


def test_faces_defaults_to_a_wrapped_column_everywhere():
    """Default 4 in the signature, the schema and the column default, so no
    existing row moves and only a pilaster has to say anything."""
    L, W, H = Decimal("18"), Decimal("24"), Decimal("12")
    assert cv.form_sf(H, L, W, 1) == cv.form_sf(H, L, W, 1, 4)
    assert cv.chamfer_lf(H, 1) == cv.chamfer_lf(H, 1, 4)
    assert cv.formed_perimeter_in(L, W) == cv.formed_perimeter_in(L, W, 4)


def test_the_lbj_columns_section_does_not_move(db, estimate):
    """68 wrapped columns. sql/051 defaults every existing row to 4, so the
    golden section is the proof that adding the field moved nothing."""
    from tests.test_columns import APP

    section = _build(db, estimate)
    assert all(t.formed_faces == 4 for t in _types(db, section.id))
    assert _cost(db, section.id) == APP["total_cost"]


# ------------------------------------------- what the face count reaches ----


def test_wall_side_types_reduce_form_area_and_everything_that_rides_it(db, estimate):
    """
    The reason this is a field and not a plywood tweak. Form SF is the
    allocation basis, so turning a section's types into pilasters moves labor,
    lumber, nails and the section's share of every shared cost at once.
    """
    section = _build(db, estimate)
    before_sf = Decimal(str(cv.section_column_totals(db, section.id)["total_form_sf"]))
    before_cost = _cost(db, section.id)
    before_forming = {
        ln["code"]: Decimal(str(ln["qty"]))
        for ln in load_stored_forming(db, section.id)["lines"]
    }

    for t in _types(db, section.id):
        t.formed_faces = 3
    db.flush()
    recalc_section(db, section)
    db.flush()

    after = cv.section_column_totals(db, section.id)
    after_sf = Decimal(str(after["total_form_sf"]))
    assert after_sf < before_sf, "a wall side is form you do not build"
    assert _cost(db, section.id) < before_cost

    # ...and it reached the takeoffs, not just the header figure.
    after_forming = {
        ln["code"]: Decimal(str(ln["qty"]))
        for ln in load_stored_forming(db, section.id)["lines"]
    }
    assert after_forming["2x4"] < before_forming["2x4"]
    assert after_forming["chamfer"] < before_forming["chamfer"]

    labor_sf = db.execute(
        text("SELECT qty FROM estimate_labor_lines "
             "WHERE section_id = :s AND code = 'forming'"),
        {"s": str(section.id)},
    ).scalar()
    assert Decimal(str(labor_sf)) == after_sf, "labor rides the same contact area"


def test_concrete_and_steel_do_not_move_with_the_face_count(db, estimate):
    """A pilaster is the same lump of concrete and the same cage whichever
    side of it you form. Only the FORMING follows the faces."""
    section = _build(db, estimate)
    before = cv.section_column_totals(db, section.id)

    for t in _types(db, section.id):
        t.formed_faces = 2
    db.flush()
    recalc_section(db, section)
    db.flush()
    after = cv.section_column_totals(db, section.id)

    assert after["total_concrete_cy"] == before["total_concrete_cy"]
    assert after["total_rebar_lb"] == before["total_rebar_lb"]
    assert after["total_form_sf"] < before["total_form_sf"]


def test_one_section_can_hold_both_a_column_and_a_pilaster(db, estimate):
    """"Varies by job" — so it is per TYPE, not a switch on the section. A
    wall-side type and a wrapped one of identical size differ only by faces."""
    section = _build(db, estimate)
    types = _types(db, section.id)
    a, b = types[0], types[1]
    b.length_in, b.width_in, b.height_ft, b.qty = a.length_in, a.width_in, a.height_ft, a.qty
    b.formed_faces = 3
    db.flush()
    recalc_section(db, section)
    db.flush()
    db.refresh(a); db.refresh(b)

    assert a.formed_faces == 4 and b.formed_faces == 3
    assert Decimal(str(b.calc_form_sf)) < Decimal(str(a.calc_form_sf))
    assert Decimal(str(b.calc_concrete_cy)) == Decimal(str(a.calc_concrete_cy))


# ----------------------------------------------------------- haul-off ----


def test_a_pilaster_section_can_switch_haul_off_on(client, db, estimate):
    """The other half of the pilaster story. Off for a columns section (a
    column has no spoil); a pilaster digs, so it is one checkbox."""
    section = _build(db, estimate)
    lines = {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}
    assert lines["haul_off"]["enabled"] is False

    r = client.patch(
        f"/api/sections/{section.id}/equipment/lines/haul_off",
        json={"enabled": True, "days_qty": 25},
    )
    assert r.status_code == 200, r.text
    after = {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}
    assert after["haul_off"]["enabled"] is True
    assert Decimal(str(after["haul_off"]["ext_cost"])) > 0


# ---------------------------------------------------------------- API ----


def test_the_api_round_trips_faces_and_refuses_nonsense(client, db, estimate):
    section = _build(db, estimate)
    row = _types(db, section.id)[0]

    r = client.patch(f"/api/column-types/{row.id}", json={"formed_faces": 3})
    assert r.status_code == 200, r.text
    assert r.json()["formed_faces"] == 3

    # 1 face is not a thing you can form, and 5 is not a shape.
    assert client.patch(f"/api/column-types/{row.id}", json={"formed_faces": 1}).status_code == 422
    assert client.patch(f"/api/column-types/{row.id}", json={"formed_faces": 5}).status_code == 422


def test_a_new_type_is_a_column_unless_it_says_otherwise(client, db, estimate, project):
    """A pilaster is the exception, so it is the one that has to be typed."""
    section = _build(db, estimate)
    r = client.post(
        "/api/column-types",
        json={"section_id": str(section.id), "label": "P1", "qty": 4,
              "height_ft": 10, "length_in": 18, "width_in": 12},
    )
    assert r.status_code == 201, r.text
    assert r.json()["formed_faces"] == 4
