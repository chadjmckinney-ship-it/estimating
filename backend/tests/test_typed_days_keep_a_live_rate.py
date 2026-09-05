"""
A typed quantity pins the quantity. It no longer pins the rate. (sql/058)

Found by the 2026-09-04 full check. `update_labor_line` set `is_manual` when
EITHER a qty or a rate arrived, and the refresh kept `rate` on every manual
row. On piers, walls and decks the superintendent's days have to be typed —
there is no area to derive them from, and the unpriced list demands it — so
every supervision line on those sections was manual from its first entry,
and a later change to `labor_super_day_rate`, on the price sheet or in
company settings, never reached it. The rates card said $475; the line kept
billing $425; nothing on screen disagreed. Equipment had the same shape:
giving a machine days froze its day rate.

The screen made it worse. Every Save sent the rate box back whether or not
anybody had touched it, so "typed the days" and "typed the rate" were the
same request. app.js now sends only what changed — and the enabled checkbox
sends `mark_manual: null` rather than `false`, because `false` is the API's
"hand this line back", which un-pinned typed days on every toggle.

The rule now: `is_manual` pins the quantity and the switch; `rate_is_manual`
pins the rate; a refresh re-resolves every rate that was not typed.

The golden fixtures type their days at the company rate, so this change moves
none of their numbers — `test_piers`, `test_walls` and `test_cip_deck` are the
proof, and this file is the direction they never checked.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db import get_db
from app.main import app
from app.models.estimate_price import EstimatePrice
from app.services import price_book as pb
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
    update_equipment_line,
)
from app.services.forming import refresh_and_store_forming
from app.services.labor import (
    load_stored_labor,
    refresh_and_store_labor,
    update_labor_line,
)
from app.services.recalc import recalc_section
from tests import columns_fixture as cf
from tests import piers_fixture as pf

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _piers(db, estimate):
    """A piers section with its days typed, the way a person does it."""
    section = pf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    pf.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _columns(db, estimate):
    section = cf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def _labor(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, section_id)["lines"]}


def _equip(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, section_id)["lines"]}


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _rate_row(db, estimate_id, key, scope) -> EstimatePrice:
    """
    The sheet row that governs `key` for a section of kind `scope`: the
    assembly's own row when it has one, else the company's.
    """
    for kind, sc in (("assembly_rate", scope), ("setting", None)):
        row = db.scalars(
            select(EstimatePrice).where(
                EstimatePrice.estimate_id == estimate_id,
                EstimatePrice.kind == kind,
                EstimatePrice.scope == sc,
                EstimatePrice.ref_key == key,
            )
        ).first()
        if row is not None:
            return row
    raise AssertionError(f"{key} is not on the sheet")


def _machine_row(db, estimate_id, label_prefix) -> EstimatePrice:
    row = db.scalars(
        select(EstimatePrice).where(
            EstimatePrice.estimate_id == estimate_id,
            EstimatePrice.kind == "equipment",
            EstimatePrice.label.ilike(f"{label_prefix}%"),
        )
    ).first()
    assert row is not None, f"{label_prefix} is not on the sheet"
    return row


# ------------------------------------------------------------------ labor ----


def test_typed_days_pin_the_days_and_not_the_rate(db, estimate):
    section = _piers(db, estimate)
    sup = _labor(db, section.id)["superintendent"]
    assert D(str(sup["qty"])) == pf.SUPER_DAYS
    assert sup["is_manual"] is True
    assert sup["rate_is_manual"] is False
    assert D(str(sup["rate"])) == D("425")


def test_a_day_rate_change_on_the_sheet_reaches_a_typed_superintendent(db, estimate):
    """
    The bug. "On this job the super is $475" — and on a section whose days are
    typed, that used to change nothing.
    """
    section = _piers(db, estimate)
    before = _cost(db, section.id)

    row = _rate_row(db, estimate.id, "labor_super_day_rate", section.kind)
    assert D(str(row.value)) == D("425")
    pb.set_price(db, row, value=D("475"), note="two supers' worth")
    recalc_section(db, section)
    db.flush()

    sup = _labor(db, section.id)["superintendent"]
    assert D(str(sup["qty"])) == pf.SUPER_DAYS, "the typed days survived the refresh"
    assert sup["is_manual"] is True
    assert D(str(sup["rate"])) == D("475"), "the rate followed the sheet"
    assert D(str(sup["ext_cost"])) == (pf.SUPER_DAYS * D("475")).quantize(D("0.01"))
    # Supervision is untaxed and carries no fuel, so the section moves by
    # exactly the difference — days × $50 — and nothing else.
    assert _cost(db, section.id) - before == (pf.SUPER_DAYS * D("50")).quantize(D("0.01"))


def test_a_typed_rate_stays_pinned(db, estimate):
    """The half that has to keep working: a rate the estimator typed is theirs."""
    section = _piers(db, estimate)
    update_labor_line(db, section.id, "superintendent", rate=D("500"), mark_manual=True)
    sup = _labor(db, section.id)["superintendent"]
    assert sup["rate_is_manual"] is True

    row = _rate_row(db, estimate.id, "labor_super_day_rate", section.kind)
    pb.set_price(db, row, value=D("475"))
    recalc_section(db, section)
    db.flush()

    sup = _labor(db, section.id)["superintendent"]
    assert D(str(sup["rate"])) == D("500")
    assert D(str(sup["qty"])) == pf.SUPER_DAYS
    assert D(str(sup["ext_cost"])) == (pf.SUPER_DAYS * D("500")).quantize(D("0.01"))


def test_handing_the_line_back_clears_both_pins(db, estimate):
    section = _piers(db, estimate)
    update_labor_line(db, section.id, "superintendent", rate=D("500"), mark_manual=True)
    update_labor_line(db, section.id, "superintendent", mark_manual=False)
    refresh_and_store_labor(db, section.id)

    sup = _labor(db, section.id)["superintendent"]
    assert sup["is_manual"] is False
    assert sup["rate_is_manual"] is False
    assert D(str(sup["rate"])) == D("425"), "back on the ladder"


def test_the_api_says_which_half_is_pinned(client, db, estimate):
    section = _piers(db, estimate)
    url = f"/api/sections/{section.id}/labor/lines/foreman"

    r = client.patch(url, json={"qty": "12"})
    assert r.status_code == 200, r.text
    line = {x["code"]: x for x in r.json()["lines"]}["foreman"]
    assert line["is_manual"] is True and line["rate_is_manual"] is False
    assert D(line["qty"]) == D("12")

    r = client.patch(url, json={"rate": "260"})
    line = {x["code"]: x for x in r.json()["lines"]}["foreman"]
    assert line["is_manual"] is True and line["rate_is_manual"] is True

    r = client.patch(url, json={"mark_manual": False})
    line = {x["code"]: x for x in r.json()["lines"]}["foreman"]
    assert line["is_manual"] is False and line["rate_is_manual"] is False


def test_the_switch_from_the_screen_leaves_the_pins_alone(client, db, estimate):
    """
    What app.js sends on the enabled checkbox since 2026-09-04: `null`. It
    used to send `false`, which is the API's hand-it-back — so unticking and
    re-ticking a typed foreman un-pinned the 10 days somebody typed.
    """
    section = _piers(db, estimate)
    url = f"/api/sections/{section.id}/labor/lines/foreman"
    assert _labor(db, section.id)["foreman"]["is_manual"] is True

    r = client.patch(url, json={"enabled": False, "mark_manual": None})
    assert r.status_code == 200, r.text
    line = {x["code"]: x for x in r.json()["lines"]}["foreman"]
    assert line["enabled"] is False
    assert line["is_manual"] is True, "a switch is not an override"
    assert D(line["qty"]) == pf.FOREMAN_DAYS

    # ...and `false` still means what it always meant, for the caller that
    # wants it: hand the line back.
    r = client.patch(url, json={"enabled": True, "mark_manual": False})
    line = {x["code"]: x for x in r.json()["lines"]}["foreman"]
    assert line["is_manual"] is False


# -------------------------------------------------------------- equipment ----


def test_typed_equipment_days_keep_a_live_rate(db, estimate):
    """
    Give a machine days — the intended workflow for one that ships off — and
    its rate must keep following the sheet. It used to freeze at the day the
    days went in.
    """
    section = _columns(db, estimate)
    update_equipment_line(db, section.id, "skytrack", days_qty=D("9"), mark_manual=True)
    sky = _equip(db, section.id)["skytrack"]
    assert sky["is_manual"] is True and sky["rate_is_manual"] is False
    assert D(str(sky["days_qty"])) == D("9")

    row = _machine_row(db, estimate.id, "SkyTrack")
    assert D(str(sky["rate"])) == D(str(row.value))
    pb.set_price(db, row, value=D("999"))
    refresh_and_store_equipment(db, section.id)

    sky = _equip(db, section.id)["skytrack"]
    assert D(str(sky["days_qty"])) == D("9"), "the typed days survived"
    assert D(str(sky["rate"])) == D("999"), "the rate followed the sheet"
    assert sky["price_source"] == "sheet"
    assert D(str(sky["ext_cost"])) == (D(str(sky["billable_units"])) * D("999")).quantize(D("0.01"))


def test_a_typed_equipment_rate_stays_pinned(db, estimate):
    section = _columns(db, estimate)
    update_equipment_line(db, section.id, "skytrack", rate=D("777"), mark_manual=True)
    row = _machine_row(db, estimate.id, "SkyTrack")
    pb.set_price(db, row, value=D("999"))
    refresh_and_store_equipment(db, section.id)

    sky = _equip(db, section.id)["skytrack"]
    assert sky["rate_is_manual"] is True
    assert D(str(sky["rate"])) == D("777")
    assert sky["price_source"] == "manual"


def test_a_placeholder_rate_on_a_machine_given_days_still_reads_as_one(db, estimate):
    """
    The manual branch used to stamp `price_source="manual"` on every manual
    row, so a code-default rate on a machine somebody gave days stopped being
    flagged. A placeholder is a placeholder however the days got there.
    """
    section = _columns(db, estimate)
    # Off the sheet: the machine and any rate row for it (test_stage0_groundwork).
    db.execute(
        text(
            "DELETE FROM estimate_prices WHERE estimate_id = :e AND ("
            "(kind = 'equipment' AND label ILIKE 'SkyTrack%') OR "
            "ref_key = 'equip_skytrack_day_rate')"
        ),
        {"e": str(estimate.id)},
    )
    db.flush()
    update_equipment_line(db, section.id, "skytrack", days_qty=D("9"), mark_manual=True)
    refresh_and_store_equipment(db, section.id)

    sky = _equip(db, section.id)["skytrack"]
    assert sky["is_manual"] is True
    assert sky["price_source"] == "default"
    assert sky["missing_price"] is True


# ------------------------------------------------------------ the screen ----


def test_every_line_the_screen_reads_says_whether_its_rate_is_typed(client, db, estimate):
    """The schema-drop guard for the new field, on both cards."""
    section = _piers(db, estimate)
    labor = client.get(f"/api/sections/{section.id}/labor").json()
    assert labor["lines"] and all("rate_is_manual" in ln for ln in labor["lines"])
    equip = client.get(f"/api/sections/{section.id}/equipment").json()
    assert equip["lines"] and all("rate_is_manual" in ln for ln in equip["lines"])
