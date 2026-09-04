"""
The company settings screen (sql/054) — and the one thing it has to get right.

Chad, 2026-09-04: **"yes, build the company settings section."**

It exists because sql/053 shipped `mobilization_ls` with no way to set it. The
only settings UI in the app was the vapor-tape picker, and half a dozen figures
that decide what every bid costs — the tax rate, the fuel uplift, the
supervision day rates — were reachable only through the database.

## The pair that matters

A **price** is frozen on each estimate's price sheet at its pull, so changing
it here sets what NEW work is priced at and leaves existing jobs alone. A
**rule** is read live, so changing it rewrites every open estimate on the
spot.

Same screen, opposite consequences. Getting them the wrong way round is how
somebody raises a rate, sees the job not move, and raises it again — so the
two tests at the bottom of this file are the point of the whole thing, and
everything above them is the metadata that lets the screen say which is which.

The taxonomy is SERVED, not re-derived in JavaScript, for the same reason
`quote_kinds` is served on a section: a second copy of the split that decides
the money is a copy that will disagree.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services import price_book as pb
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.recalc import settings_scope

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _rows(client) -> dict[str, dict]:
    r = client.get("/api/system-settings")
    assert r.status_code == 200, r.text
    return {row["key"]: row for row in r.json()}


def _build(db, estimate, mod_name="columns_fixture"):
    import importlib

    mod = importlib.import_module(f"tests.{mod_name}")
    section = mod.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    if hasattr(mod, "type_the_supervision"):
        mod.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


# ------------------------------------------------------------- metadata ----


def test_every_setting_says_whether_it_is_a_price_or_a_rule(client):
    """
    The badge on every row. A key that is neither would render with no badge
    and no explanation of what editing it does — `test_price_sheet_rates`
    already fails the day one appears, and this is the screen's own guard.
    """
    rows = _rows(client)
    assert rows, "the migrations seed system_settings"
    odd = [k for k, r in rows.items() if r["unclassified"]]
    assert odd == [], odd

    for key, r in rows.items():
        assert r["is_price"] == (key in pb.MONETARY_KEYS), key
        # A price carries the registry's label and unit; a rule has neither,
        # because a waste factor is a ratio and a divisor is a count.
        if r["is_price"]:
            assert r["label"] and r["unit"], key
        else:
            assert r["label"] is None and r["unit"] is None, key


def test_every_setting_is_filed_somewhere_and_the_money_sorts_first(client):
    """
    Group and order are served, because the ORDER is a judgement — the tax
    rate before the vapor-barrier defaults — and alphabetical is not it. The
    page used to open on "Vapor barrier", which is nobody's first question.
    """
    rows = _rows(client)
    assert all(r["group"] != "Other" for r in rows.values()), [
        k for k, r in rows.items() if r["group"] == "Other"
    ]

    order = {}
    for r in rows.values():
        order.setdefault(r["group"], r["group_order"])
    # One order per group, and the two ratios that turn quantities into money
    # come first.
    assert len({r["group_order"] for r in rows.values() if r["group"] == "Supervision"}) == 1
    assert min(order, key=order.get) == "Tax & uplifts"
    assert order["Mobilization"] < order["Vapor barrier"]


def test_every_setting_says_what_editing_it_rewrites(client):
    """
    `scope` comes from `services/recalc.settings_scope`, so the screen can say
    "this rewrites every open estimate" BEFORE the click rather than after it.
    """
    rows = _rows(client)
    for key, r in rows.items():
        assert r["scope"] == settings_scope([key]), key

    # A waste factor moves the quantities, so it moves everything.
    assert all(rows["waste_concrete"]["scope"].values())
    # A day rate moves labor, and equipment days ride the supervision duration.
    assert rows["labor_super_day_rate"]["scope"]["labor"]
    assert rows["labor_super_day_rate"]["scope"]["equipment"]


def test_mobilization_reaches_the_equipment_lines(client):
    """
    A regression guard on sql/053. `mobilization_ls` is neither `labor_*` nor
    `equip_*`, so the prefix rules in `settings_scope` would have called it
    "a key that feeds no stored calculation" — and a company rate change that
    rewrites nothing is one nobody notices did nothing.
    """
    assert settings_scope(["mobilization_ls"]) == {
        "pours": False, "forming": False, "labor": False, "equipment": True,
    }
    assert _rows(client)["mobilization_ls"]["scope"]["equipment"] is True


# -------------------------------------------------- unset is not zero ----


def test_a_key_with_no_value_reads_as_unset_not_as_zero(client):
    """
    `mobilization_ls` ships as jsonb null (sql/053). The screen draws it dim
    with a "not set" placeholder, and it must never draw it as 0 — a company
    with no mobilization figure is a different thing from one that mobilizes
    for free.
    """
    row = _rows(client)["mobilization_ls"]
    assert row["is_set"] is False
    assert row["value"] is None


def test_a_price_can_be_set_and_cleared_again(client):
    """
    Clearing is the half that is easy to leave out, and leaving it out is how
    a guessed number becomes permanent. `null` restores unset; it is not the
    same as saving a zero.
    """
    r = client.patch("/api/system-settings/mobilization_ls", json={"value": "1850"})
    assert r.status_code == 200, r.text

    row = _rows(client)["mobilization_ls"]
    assert row["is_set"] is True and row["value"] == "1850"

    r = client.patch("/api/system-settings/mobilization_ls", json={"value": None})
    assert r.status_code == 200, r.text
    row = _rows(client)["mobilization_ls"]
    assert row["is_set"] is False and row["value"] is None

    # ...and cleared is NOT zero: a zero would price mobilization at free.
    client.patch("/api/system-settings/mobilization_ls", json={"value": "0"})
    row = _rows(client)["mobilization_ls"]
    assert row["is_set"] is True and row["value"] == "0"


def test_an_unknown_key_is_refused(client):
    """Settings are seeded by migration. Inventing one here would create a
    value nothing reads."""
    r = client.patch("/api/system-settings/not_a_real_key", json={"value": "1"})
    assert r.status_code == 404


# ------------------------------------------- the pair that matters ----


def test_changing_a_PRICE_does_not_move_a_sheeted_estimate(client, db, estimate):
    """
    The whole reason the price sheet exists. A bid that has gone out keeps the
    numbers it was bid with, so raising the superintendent's day rate here
    changes what NEW work is priced at and leaves this job exactly where it is.

    If this ever fails, every archived bid in the system just moved.
    """
    section = _build(db, estimate)
    before = _cost(db, section.id)
    assert before and before > 0

    r = client.patch("/api/system-settings/labor_super_day_rate", json={"value": "900"})
    assert r.status_code == 200, r.text
    db.expire_all()

    assert _cost(db, section.id) == before, "a sheeted estimate must not move"
    # ...and the job knows the master has moved, rather than the change being
    # invisible: the drift check is what turns "frozen" into "frozen on
    # purpose".
    moved = pb.drift(db, estimate.id)
    assert any(
        d.get("ref_key") == "labor_super_day_rate" for d in moved.changed
    ), moved.changed


def test_a_pull_is_what_lets_a_price_change_reach_an_open_job(client, db, estimate):
    """The other half. Frozen is not stuck — pulling the sheet takes the new
    number, deliberately and on the estimator's say-so."""
    section = _build(db, estimate)
    before = _cost(db, section.id)

    client.patch("/api/system-settings/labor_super_day_rate", json={"value": "900"})
    pb.pull_prices(db, estimate.id)
    from app.services.recalc import recalc_section

    recalc_section(db, section)
    db.flush()

    assert _cost(db, section.id) > before


def test_changing_a_RULE_rewrites_the_open_estimates(client, db, estimate):
    """
    The opposite consequence, on the same screen. The support-steel allowance
    is how the work is COMPUTED rather than what it costs, so a correction has
    to reach the jobs it was wrong on — and the save says how many it reached.

    This key and not `waste_concrete`, deliberately: every assembly except the
    mono slab overrides waste in `assembly_rates`, and every fixture pins its
    own on the section besides. A company rule that three layers already
    answer would prove nothing here. `support_rebar_lb_per_sf` is a rule with
    no section column and no mono-slab override, so the company figure is
    genuinely the one in charge — which is what this test needs to be about.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    db.commit()
    before = _cost(db, section.id)

    r = client.patch(
        "/api/system-settings/support_rebar_lb_per_sf", json={"value": "0.5"}
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert all(report["scope"].values()), report["scope"]
    assert report["recalculated"], "a rule change has to rewrite something"

    db.expire_all()
    assert _cost(db, section.id) > before, "more support steel is more steel"


def test_a_frozen_bid_is_left_alone_even_by_a_rule(client, db, estimate):
    """
    The line the sweep will not cross. A final or archived estimate keeps its
    numbers whatever the company changes; repricing one is its own button on
    its own page.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    db.execute(
        text("UPDATE estimates SET status = 'final' WHERE id = :i"),
        {"i": str(estimate.id)},
    )
    db.commit()
    before = _cost(db, section.id)

    # The same rule that moves an open job in the test above.
    r = client.patch(
        "/api/system-settings/support_rebar_lb_per_sf", json={"value": "0.9"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["skipped"], "a final bid should be reported as skipped"

    db.expire_all()
    assert _cost(db, section.id) == before


def test_saving_without_recalculating_says_the_estimates_are_stale(client):
    """The batch path. Turning recalc off is for making several edits and
    sweeping once — and it says so, because a silent stale total is the
    failure this whole app keeps hunting."""
    r = client.patch(
        "/api/system-settings/support_rebar_lb_per_sf?recalc=false",
        json={"value": "0.11"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recalculated"] == []
    assert "stale" in (body["note"] or "").lower()
