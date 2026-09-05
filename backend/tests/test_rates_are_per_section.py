"""
Rates are always per section. Chad, 2026-09-05.

The ladder (sql/055) let a section override any rate, but a section that had
not spoken inherited its kind's rates from the job's sheet, the assembly and
the company — and followed them forever, so editing the walls forming rate on
the job sheet moved every walls section on the job. Chad: "labor needs to be
per section" — "Rates are always per section. go."

So a new section takes every section-level PRICE it reads at today's resolved
value and owns it from there (services/section_rates.seed, called by the
create route). Supervision day rates are the job's (ESTIMATE_LEVEL_KEYS, on
his "supervision, equipment, materials are all project specific pricing"),
rules are read live by design, and neither is seeded. Existing sections were
seeded by backend/seed_section_rates.py at what they resolved to, so no
number moved on the way in.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services import section_rates as sr
from tests import walls_fixture as wf

D = Decimal
SUPERVISION = {
    "labor_super_day_rate", "labor_foreman_day_rate",
    "labor_pm_day_rate", "labor_expense_day_rate",
}


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _new_section(client, estimate, name="W") -> str:
    r = client.post(
        f"/api/estimates/{estimate.id}/sections",
        json={"kind": "walls_footings", "name": name, "unit": "FF"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _rates(client, sid) -> dict:
    r = client.get(f"/api/sections/{sid}/rates")
    assert r.status_code == 200, r.text
    return {row["key"]: row for row in r.json()["rows"]}


def _fallback(row) -> Decimal:
    """What the ladder would say without the section's own value."""
    for v in (row["job_value"], row["assembly_value"], row["company_value"], row["default_value"]):
        if v is not None:
            return D(str(v))
    raise AssertionError(f"{row['key']} has no rung under it")


def test_a_new_section_owns_every_price_it_reads(client, db, estimate):
    sid = _new_section(client, estimate)
    rows = _rates(client, sid)
    prices = [
        k for k, v in rows.items()
        if v["is_price"] and v["level"] == "section" and v["was_read"]
    ]
    assert "labor_forming_sf" in prices and "labor_footings_sf" in prices, prices
    for k in prices:
        assert rows[k]["source"] == "section", k
        assert (rows[k]["note"] or "").startswith("seeded"), (k, rows[k]["note"])
        # ...at exactly what the ladder said the moment it was created
        assert D(str(rows[k]["section_value"])) == _fallback(rows[k]), k


def test_supervision_day_rates_and_rules_are_not_the_sections_to_own(client, db, estimate):
    rows = _rates(client, _new_section(client, estimate))
    for k in SUPERVISION & set(rows):
        assert rows[k]["level"] == "estimate", k
        assert rows[k]["source"] != "section", k
    for k, v in rows.items():
        if not v["is_price"]:
            assert v["source"] != "section", f"{k} is a rule — read live, never seeded"


def test_a_later_change_to_the_kinds_rate_does_not_move_an_existing_section(client, db, estimate):
    """
    The assembly moves after the section exists: the section keeps what it
    was seeded with, and a section made after the move starts at the new
    number. This is the whole point.
    """
    a = _new_section(client, estimate, "A")
    before = _rates(client, a)["labor_forming_sf"]
    assert before["source"] == "section"
    was = D(str(before["value"]))

    db.execute(
        text("UPDATE assembly_rates SET value = :v WHERE kind = 'walls_footings' AND key = 'labor_forming_sf'"),
        {"v": was + D("5")},
    )
    db.flush()

    still = _rates(client, a)["labor_forming_sf"]
    assert D(str(still["value"])) == was
    assert D(str(still["assembly_value"])) == was + D("5")  # the ladder shows the move; the section ignores it

    b = _new_section(client, estimate, "B")
    assert D(str(_rates(client, b)["labor_forming_sf"]["value"])) == was + D("5")


def test_two_sections_of_one_kind_share_nothing(client, db, estimate):
    a = _new_section(client, estimate, "A")
    b = _new_section(client, estimate, "B")
    assert _rates(client, a)["labor_forming_sf"]["value"] == _rates(client, b)["labor_forming_sf"]["value"]
    r = client.put(f"/api/sections/{a}/rates/labor_forming_sf", json={"value": "4.10", "note": "cheaper sub"})
    assert r.status_code == 200, r.text
    assert D(str(_rates(client, a)["labor_forming_sf"]["value"])) == D("4.10")
    b_row = _rates(client, b)["labor_forming_sf"]
    assert D(str(b_row["value"])) != D("4.10")
    assert (b_row["note"] or "").startswith("seeded")


def test_clearing_hands_the_rate_back_to_the_ladder(client, db, estimate):
    a = _new_section(client, estimate, "A")
    r = client.delete(f"/api/sections/{a}/rates/labor_forming_sf")
    assert r.status_code == 200, r.text
    row = _rates(client, a)["labor_forming_sf"]
    assert row["source"] != "section"
    assert D(str(row["value"])) == _fallback(row)


def test_the_backfill_seeds_a_section_that_predates_the_rule_without_moving_it(client, db, estimate):
    """A fixture builds its section straight into the table — no route, no
    seeding — exactly like every section that existed before 2026-09-05."""
    section = wf.build(db, estimate)
    assert client.post(f"/api/sections/{section.id}/recalc").status_code == 200
    before = D(str(client.get(f"/api/sections/{section.id}").json()["calc_total_cost"]))
    assert before > 0
    assert not db.execute(
        text("SELECT 1 FROM section_rates WHERE section_id = :s"), {"s": str(section.id)}
    ).first()

    written = sr.seed(db, section, note="seeded (backfill test)")
    db.flush()
    assert "labor_forming_sf" in written and "labor_footings_sf" in written
    assert not (set(written) & SUPERVISION)

    assert client.post(f"/api/sections/{section.id}/recalc").status_code == 200
    after = D(str(client.get(f"/api/sections/{section.id}").json()["calc_total_cost"]))
    assert after == before, "seeding writes what the section already paid"

    assert sr.seed(db, section) == []  # safe to run twice
