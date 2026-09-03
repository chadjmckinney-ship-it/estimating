"""
The fields the columns SCREEN reads, as a contract.

Every other assembly's front end was written against a payload that already
existed. Columns is the first one where the screen and the API were written in
the same week, and the failure mode that produces is silent: `num(undefined)`
renders "—" and a card that should read 7,716 SF reads a dash, with a 200 OK on
every request and nothing in the console.

So this file is a list of key names, and it is deliberately dumb. It does not
check that the numbers are right — `test_columns.py` does that against the
sheet. It checks that the four payloads the section page fetches actually carry
the keys `app.js` reaches for, so renaming one on the server breaks a test here
instead of blanking a card on Chad's screen.

If a card is added to the columns page, add its driver here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services.costing import refresh_pour_costs
from tests import columns_fixture as colf


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def section(db, estimate):
    s = colf.build(db, estimate)
    refresh_pour_costs(db, s)
    db.flush()
    return s


# The stat cards across the top of the columns page.
TOTALS_KEYS = {
    "type_count",
    "column_count",
    "total_form_sf",
    "total_concrete_cy",
    "total_vert_rebar_lb",
    "total_tie_rebar_lb",
    "total_dowel_rebar_lb",
    "total_rebar_lb",
    "total_chamfer_lf",
    "total_cost",
    "total_sale",
    "total_cost_per_unit",
    "total_sale_per_unit",
    "cost_per_form_sf",
}

# The derived columns of the grid — the ones `columnColumns()` reads off a row.
ROW_KEYS = {
    "id",
    "label",
    "qty",
    "height_ft",
    "length_in",
    "width_in",
    "mix_design_id",
    "vert1_count", "vert1_size",
    "vert2_count", "vert2_size",
    "vert3_count", "vert3_size",
    "tie_size", "tie_spacing_in",
    "dowel_count", "dowel_size", "dowel_length_ft",
    "calc_form_sf",
    "calc_concrete_cy",
    "calc_vert_rebar_lb",
    "calc_tie_rebar_lb",
    "calc_dowel_rebar_lb",
    "calc_total_rebar_lb",
    "calc_chamfer_lf",
    "calc_cost",
    "calc_cost_per_unit",
    "calc_sale_per_unit",
}


def test_the_totals_payload_has_every_stat_card(client, section):
    r = client.get(f"/api/column-types/totals?section_id={section.id}")
    assert r.status_code == 200, r.text
    missing = TOTALS_KEYS - set(r.json())
    assert not missing, f"stat cards read fields the API does not serve: {sorted(missing)}"


def test_a_grid_row_has_every_column(client, section):
    r = client.get(f"/api/column-types?section_id={section.id}")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == len(colf.TYPES)
    missing = ROW_KEYS - set(rows[0])
    assert not missing, f"grid columns read fields the API does not serve: {sorted(missing)}"
    # Non-null is the point: a derived cell that renders "—" on a real takeoff
    # is the failure this file exists to catch.
    for key in ("calc_form_sf", "calc_concrete_cy", "calc_total_rebar_lb", "calc_chamfer_lf"):
        assert rows[0][key] is not None, f"{key} came back null on a full row"


def test_the_forming_header_reads_columns_not_a_perimeter(client, section):
    """`column_count`, `form_sf` and `chamfer_lf` drive the forming card's header."""
    r = client.get(f"/api/sections/{section.id}/forming-materials")
    assert r.status_code == 200, r.text
    d = r.json()["drivers"]
    for key in ("kind", "column_count", "form_sf", "chamfer_lf"):
        assert key in d, f"forming drivers is missing {key}"
    assert d["kind"] == "columns"


def test_the_labor_header_can_explain_the_duration(client, section):
    """
    The columns labor blurb spells the derivation out — count ÷ per week ×
    days per week — so all three have to be on the payload, not just the answer.
    """
    r = client.get(f"/api/sections/{section.id}/labor")
    assert r.status_code == 200, r.text
    d = r.json()["drivers"]
    for key in ("column_count", "form_sf", "super_days", "super_weeks",
                "sf_per_week", "days_per_week", "total_rebar_tons"):
        assert key in d, f"labor drivers is missing {key}"
    assert float(d["column_count"]) == 68
    assert float(d["days_per_week"]) == 5
    assert float(d["sf_per_week"]) == 20


def test_the_equipment_header_has_its_day_counts(client, section):
    r = client.get(f"/api/sections/{section.id}/equipment")
    assert r.status_code == 200, r.text
    d = r.json()["drivers"]
    for key in ("kind", "super_days", "equip_days", "total_concrete_cy"):
        assert key in d, f"equipment drivers is missing {key}"


def test_the_money_cards_get_their_lines(client, section):
    """Concrete and rebar are the two stat cards on this page that show dollars."""
    r = client.get(f"/api/sections/{section.id}/material-costs")
    assert r.status_code == 200, r.text
    keys = {ln["key"] for ln in r.json()["lines"]}
    assert {"concrete", "rebar"} <= keys
