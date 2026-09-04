"""
Mobilization (sql/053) — getting the iron to the job and home again.

Chad, 2026-09-04, while settling the deck's crane rate: **"we need to add a
price for mobilization."**

The workbook prices it nowhere. Every tab of the LBJ estimate was searched for
"mobil", "demob", "delivery" and "haul in": eight hits, and all eight are the
word "Mobile" beside a supplier's phone number or a box-delivery line on a PT
slab sheet. So there is no formula to reproduce here and no golden number to
land on — this is a real cost the sheets have been leaving out, on jobs that
rent a $3,200/day crane.

Three decisions, all Chad's, all 2026-09-04:

  * **one line per SECTION**, not per machine and not per job
  * **one round-trip number** — `rate` is there and back, `days_qty` is how
    many moves
  * **neither taxed nor fuelled** — it is a haul, which is work done rather
    than a thing bought, the same call sql/036 made for concrete haul-off

And one taken on the rule the app already has: the company figure starts as
jsonb null rather than a number, because a price in a migration is a second
home for a price (sql/044) and the second home is the one nobody updates.
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
from app.services.recalc import recalc_section

D = Decimal

# Every assembly. Mobilization is not a deck feature — every one of these
# brings machines to a site.
FIXTURES = [
    "mono_slab_fixture",
    "paving_fixture",
    "piers_fixture",
    "walls_fixture",
    "columns_fixture",
    "deck_fixture",
]


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate, mod_name):
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
    recalc_section(db, section)
    db.flush()
    return section


def _equip(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, section_id)["lines"]}


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _unpriced(db, section_id) -> list[str]:
    return db.execute(
        text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


# ----------------------------------------------------------- it is everywhere


@pytest.mark.parametrize("mod", FIXTURES)
def test_every_assembly_carries_a_mobilization_line(db, estimate, mod):
    """
    Not a deck feature. A pier rig, a wall crew's mini excavator and a paving
    machine all have to get to the job, and the line is built once above the
    six branches for exactly that reason — six copies is how one of them
    quietly stops having it.
    """
    section = _build(db, estimate, mod)
    line = _equip(db, section.id).get("mobilization")
    assert line is not None, f"{mod} has no mobilization line"
    assert line["label"] == "MOBILIZATION"
    assert line["unit"] == "LS"


def test_it_starts_at_zero_and_moves_nothing(db, estimate):
    """
    Adding the line to every assembly must not move a single existing bid.
    Zero moves at an unset rate is $0, and the golden columns section proves
    it — this is the whole reason the company figure is not seeded.
    """
    from tests.test_columns import APP

    section = _build(db, estimate, "columns_fixture")
    assert D(str(_equip(db, section.id)["mobilization"]["ext_cost"])) == 0
    assert _cost(db, section.id) == APP["total_cost"]


# --------------------------------------------------- unpriced, not free ----


def test_a_section_that_rents_and_does_not_mobilize_says_so(db, estimate):
    """
    The point of the whole change. A section billing 27 days of crane and
    carrying nothing for getting it there is a bid that is light, and until
    now there was nothing on screen to notice.
    """
    section = _build(db, estimate, "deck_fixture")
    flagged = _unpriced(db, section.id)
    assert any("mobilization — not entered" in x for x in flagged), flagged


def test_a_section_with_no_machines_says_nothing(db, estimate):
    """
    Flagged only where there is something to move. A warning that fires on
    every section is a warning people learn to scroll past — the same call the
    quote drift band was made on.
    """
    section = _build(db, estimate, "deck_fixture")
    db.execute(
        text(
            "UPDATE estimate_equipment_lines SET enabled = false, ext_cost = 0 "
            "WHERE section_id = :s AND group_name = 'equipment'"
        ),
        {"s": str(section.id)},
    )
    db.flush()
    recalc_section(db, section)
    db.flush()
    assert not any("mobilization" in x for x in _unpriced(db, section.id))


def test_entering_it_clears_the_warning_and_costs(client, db, estimate):
    """One move, there and back. Two phases is `2`, not a doubled rate."""
    section = _build(db, estimate, "deck_fixture")
    before = _cost(db, section.id)

    r = client.patch(
        f"/api/sections/{section.id}/equipment/lines/mobilization",
        json={"rate": "1850", "days_qty": 1},
    )
    assert r.status_code == 200, r.text

    line = _equip(db, section.id)["mobilization"]
    assert D(str(line["ext_cost"])) == D("1850.00")
    assert not any("mobilization" in x for x in _unpriced(db, section.id))
    assert _cost(db, section.id) == before + D("1850.00")


def test_two_moves_bill_twice(client, db, estimate):
    """`days_qty` is HOW MANY MOVES — a job with two phases mobilizes twice."""
    section = _build(db, estimate, "piers_fixture")
    client.patch(
        f"/api/sections/{section.id}/equipment/lines/mobilization",
        json={"rate": "1200", "days_qty": 2},
    )
    assert D(str(_equip(db, section.id)["mobilization"]["ext_cost"])) == D("2400.00")


# ------------------------------------------------- it is a haul, not a rental


def test_mobilization_is_neither_taxed_nor_fuelled(client, db, estimate):
    """
    It sits in the `contract` group, and `costing._on_takeoff_lines`
    classifies by group — so this is a property of where the line lives rather
    than a special case anybody has to remember. $1,000 of mobilization moves
    the section by exactly $1,000, not $1,082.50 and not $1,582.50.
    """
    section = _build(db, estimate, "walls_fixture")
    before = _cost(db, section.id)

    r = client.patch(
        f"/api/sections/{section.id}/equipment/lines/mobilization",
        json={"rate": "1000", "days_qty": 1},
    )
    assert r.status_code == 200, r.text
    assert _equip(db, section.id)["mobilization"]["group_name"] == "contract"
    assert _cost(db, section.id) - before == D("1000.00")


# ----------------------------------------------------- the company figure ----


def test_the_company_figure_is_deliberately_unset(db):
    """
    sql/053 creates the KEY and leaves the VALUE as jsonb null. Three things
    at once: the key exists so it can be edited and pulled; `#>> '{}'` on a
    jsonb null is SQL NULL so it reads as UNPRICED rather than as zero; and
    sql/049's numeric guard skips it rather than copying a zero onto every
    estimate's sheet.
    """
    raw = db.execute(
        text("SELECT value #>> '{}' FROM system_settings WHERE key = 'mobilization_ls'")
    ).scalar()
    assert raw is None, f"a price got committed to a migration: {raw!r}"

    with pb.catalog_only():
        from app.services.calc import _rate_optional

        assert _rate_optional(db, "cip_deck", "mobilization_ls") is None


def test_it_is_a_price_and_freezes_on_the_sheet(db, estimate):
    """
    A monetary key, so it is pulled onto the estimate's sheet and frozen there
    — the same as every other rate. Set the company figure, pull, and the job
    carries it whatever the company does next.
    """
    db.execute(
        text("UPDATE system_settings SET value = to_jsonb(CAST(:v AS text)) "
             "WHERE key = 'mobilization_ls'"),
        {"v": "1500"},
    )
    db.flush()
    pb.pull_prices(db, estimate.id)

    book = pb.load_price_book(db, estimate.id)
    assert book.has_sheet
    assert book.rate(None, "mobilization_ls") == D("1500")

    # ...and the company can move on without moving this job.
    db.execute(
        text("UPDATE system_settings SET value = to_jsonb(CAST(:v AS text)) "
             "WHERE key = 'mobilization_ls'"),
        {"v": "9999"},
    )
    db.flush()
    assert pb.load_price_book(db, estimate.id).rate(None, "mobilization_ls") == D("1500")
