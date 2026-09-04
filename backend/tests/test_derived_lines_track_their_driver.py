"""
A line nobody edited tracks its driver. Forever.

Found 2026-09-04, building a pilaster section on the LBJ job: a `columns`
section entered, refreshed, then given a different schedule and refreshed
again. Superintendent, field expense and PM all moved to the new 17 days.
The FOREMAN stayed at 5.5 — **$2,875 light**, `is_manual = false`, with the
drivers block on the very same screen reading `foreman_days: 17`.

Two special cases, one in each service, both with the same comment:

    # Special: foreman keeps previous qty if user set it once without is_manual
    if ln["code"] == "foreman" and prev is not None and prev.qty and prev.qty > 0:

    # preserve user day qty if they set without is_manual
    if prev.code in ("skytrack",) and prev.enabled and prev.days_qty > 0:

Both predate `mark_manual` on those paths. Since it exists,
`update_labor_line` and `update_equipment_line` default `mark_manual=True`, so
a quantity an estimator types is pinned by `is_manual` and preserved by the
`manuals` branch. What the special cases actually did was fire on lines nobody
had ever touched — `prev.qty > 0` is true after the first refresh — and freeze
them at whatever that first refresh computed.

So the app had two lines that stopped following their driver the moment they
first had a value, and said nothing. A takeoff that grows reprices four
supervision lines and leaves the fifth behind.

No live section on LBJ was wrong: piers and walls TYPE their foreman (properly
manual), and the slab and paving derive zero. It needed a section whose takeoff
changed after its first refresh, which is a normal Tuesday.

The rule these tests hold: **`is_manual` is the only thing that pins a
quantity.** Not "it has a value", not "it is non-zero", not the code name.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.recalc import recalc_section

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate):
    from tests import columns_fixture as cf

    section = cf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _labor(db, section_id) -> dict:
    data = load_stored_labor(db, section_id)
    return {ln["code"]: ln for ln in data["lines"]}, data["drivers"]


def _equip(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, section_id)["lines"]}


def _halve_the_schedule(db, section_id) -> None:
    """Cut every type's quantity. Columns derive supervision from the COUNT."""
    db.execute(
        text("UPDATE column_types SET qty = GREATEST(qty / 2, 1) WHERE section_id = :s"),
        {"s": str(section_id)},
    )
    db.flush()


# ------------------------------------------------------------------ foreman


def test_the_foreman_follows_the_schedule_down(db, estimate):
    """
    The bug, in its simplest form. Halve the column count and every supervision
    line has to come down together — they are all the same `super_days`.
    """
    section = _build(db, estimate)
    lines, drivers = _labor(db, section.id)
    first = D(str(lines["foreman"]["qty"]))
    assert first > 0

    _halve_the_schedule(db, section.id)
    refresh_and_store_labor(db, section.id)
    db.flush()

    lines, drivers = _labor(db, section.id)
    assert D(str(lines["foreman"]["qty"])) < first
    assert D(str(lines["foreman"]["qty"])) == D(str(drivers["foreman_days"]))


def test_every_supervision_line_moves_together(db, estimate):
    """
    What made this one hard to see: four of the five DID move. A single line
    sitting still in a block that all reads off one driver looks like a number
    somebody meant.
    """
    section = _build(db, estimate)
    _halve_the_schedule(db, section.id)
    refresh_and_store_labor(db, section.id)
    db.flush()

    lines, drivers = _labor(db, section.id)
    days = D(str(drivers["super_days"]))
    for code in ("superintendent", "foreman", "expense", "pm"):
        assert D(str(lines[code]["qty"])) == days, code


def test_the_foreman_still_follows_it_up(db, estimate):
    """Both directions — a schedule that grows was the live case."""
    section = _build(db, estimate)
    _halve_the_schedule(db, section.id)
    refresh_and_store_labor(db, section.id)
    db.flush()
    small = D(str(_labor(db, section.id)[0]["foreman"]["qty"]))

    db.execute(
        text("UPDATE column_types SET qty = qty * 4 WHERE section_id = :s"),
        {"s": str(section.id)},
    )
    db.flush()
    refresh_and_store_labor(db, section.id)
    db.flush()

    lines, drivers = _labor(db, section.id)
    assert D(str(lines["foreman"]["qty"])) > small
    assert D(str(lines["foreman"]["qty"])) == D(str(drivers["foreman_days"]))


def test_a_typed_foreman_is_still_pinned(client, db, estimate):
    """
    The half that has to keep working. Piers and walls TYPE their foreman days
    — a PATCH marks the line manual, and a refresh must not walk over it. That
    is what `is_manual` is for, and removing the special case must not remove
    it.
    """
    section = _build(db, estimate)
    r = client.patch(
        f"/api/sections/{section.id}/labor/lines/foreman", json={"qty": "42"}
    )
    assert r.status_code == 200, r.text
    assert _labor(db, section.id)[0]["foreman"]["is_manual"] is True

    _halve_the_schedule(db, section.id)
    refresh_and_store_labor(db, section.id)
    db.flush()
    assert D(str(_labor(db, section.id)[0]["foreman"]["qty"])) == D("42")


def test_handing_the_foreman_back_resumes_tracking(client, db, estimate):
    """
    `mark_manual=false` is the only way to undo an override, and after it the
    line has to start following the driver again — otherwise "hand it back"
    hands it back to a frozen number.
    """
    section = _build(db, estimate)
    client.patch(f"/api/sections/{section.id}/labor/lines/foreman", json={"qty": "42"})
    client.patch(
        f"/api/sections/{section.id}/labor/lines/foreman",
        json={"qty": "42", "mark_manual": False},
    )
    refresh_and_store_labor(db, section.id)
    db.flush()

    lines, drivers = _labor(db, section.id)
    assert lines["foreman"]["is_manual"] is False
    assert D(str(lines["foreman"]["qty"])) == D(str(drivers["foreman_days"]))


# ----------------------------------------------------------------- skytrack


def test_skytrack_follows_the_rental_ladder(db, estimate):
    """
    Same special case, same service-shaped comment, same result: 14 days kept
    from a takeoff that had since grown to 30. The rental ladder rides
    supervision days, so it has to move when they do.
    """
    section = _build(db, estimate)
    first = D(str(_equip(db, section.id)["skytrack"]["days_qty"]))
    assert first > 0

    _halve_the_schedule(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    db.flush()

    assert D(str(_equip(db, section.id)["skytrack"]["days_qty"])) < first


def test_a_typed_skytrack_is_still_pinned(client, db, estimate):
    """The other half, again — an estimator's days survive a refresh."""
    section = _build(db, estimate)
    r = client.patch(
        f"/api/sections/{section.id}/equipment/lines/skytrack", json={"days_qty": "9"}
    )
    assert r.status_code == 200, r.text

    _halve_the_schedule(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    db.flush()
    assert D(str(_equip(db, section.id)["skytrack"]["days_qty"])) == D("9")


def test_two_sections_with_the_same_takeoff_cost_the_same(db, estimate):
    """
    The check that found it, kept as a test.

    A second `columns` section holding the same schedule — which is exactly
    what a pilaster section is (sql/051) — must cost what the first one costs.
    Before the fix it came out $4,892.69 light, all of it in two lines nobody
    had touched.
    """
    from tests import columns_fixture as cf

    a = _build(db, estimate)

    b = cf.build(db, estimate)
    b.name = "Pilasters"
    db.flush()

    # The shape that triggers it: the lines get a value, THEN the schedule
    # changes, then it changes back. Every quantity ends where it started, so
    # anything still different is a line that stopped tracking.
    refresh_and_store_labor(db, b.id)
    refresh_and_store_equipment(db, b.id)
    db.execute(
        text("UPDATE column_types SET qty = 1 WHERE section_id = :s"), {"s": str(b.id)}
    )
    db.flush()
    refresh_and_store_labor(db, b.id)
    refresh_and_store_equipment(db, b.id)

    # Put the schedule back to A's, type for type.
    for label, qty in db.execute(
        text("SELECT label, qty FROM column_types WHERE section_id = :s"),
        {"s": str(a.id)},
    ).all():
        db.execute(
            text(
                "UPDATE column_types SET qty = :q "
                "WHERE section_id = :s AND label = :l"
            ),
            {"q": qty, "s": str(b.id), "l": label},
        )
    db.flush()

    refresh_and_store_forming(db, b.id)
    refresh_and_store_labor(db, b.id)
    refresh_and_store_equipment(db, b.id)
    refresh_pour_costs(db, b)
    db.flush()
    recalc_section(db, b)
    db.flush()

    def cost(sid):
        return db.execute(
            text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
            {"i": str(sid)},
        ).scalar()

    assert cost(b.id) == cost(a.id)
