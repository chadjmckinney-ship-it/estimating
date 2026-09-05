"""
The fields the CIP deck SCREEN reads, as a contract.

Same job as `test_columns_ui_contract.py`, and for the same reason: the screen
and the API were written in the same week, and the failure mode that produces
is silent. `num(undefined)` renders an em dash, so a card that should read
64,909 lb reads "—" with a 200 OK on every request and nothing in the console.

Deliberately dumb. It does not check that any number is right — `test_cip_deck`
does that against the sheet. It checks that the payloads the section page
fetches carry the keys `app.js` reaches for, so renaming one on the server
breaks a test here instead of blanking a card on Chad's screen.

If a card is added to the deck page, add its driver here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from tests import deck_fixture as df


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def section(db, estimate):
    s = df.build(db, estimate)
    refresh_and_store_forming(db, s.id)
    refresh_and_store_labor(db, s.id)
    refresh_and_store_equipment(db, s.id)
    df.type_the_supervision(db, s.id)
    refresh_pour_costs(db, s)
    db.flush()
    return s


# The stat cards across the top of the deck page.
TOTALS_KEYS = {
    "level_count",
    "total_sf",
    "total_slab_cy",
    "total_beam_cy",
    "total_concrete_cy",
    "total_slab_rebar_lb",
    "total_beam_rebar_lb",
    "total_rebar_lb",
    "total_rebar_tons",
    "total_pt_sf",
    "total_pt_lb",
    "total_perm_edge_lf",
    "total_gb_form_ff",
    # perm edge LF + GB form FF. Its own card, because every lumber line on
    # the section rides it and nothing else on the page says so.
    "lumber_driver_lf",
    "total_cost",
    "total_sale",
    "total_cost_per_unit",
    "total_sale_per_unit",
}

# The grid. Editable fields plus every derived column it displays.
ROW_KEYS = {
    "id",
    "label",
    "area_sf",
    "thickness_in",
    "has_cable",
    "mix_design_id",
    "perm_edge_lf",
    "top_bar_size",
    "top_bar_spacing_in",
    "bot_bar_size",
    "bot_bar_spacing_in",
    "mesh_sf",
    "stud_rail_lb",
    "carton_form_sf",
    "beams",
    "calc_slab_cy",
    "calc_beam_cy",
    "calc_concrete_cy",
    "calc_slab_rebar_lb",
    "calc_beam_rebar_lb",
    "calc_total_rebar_lb",
    "calc_pt_sf",
    "calc_pt_lb",
    "calc_gb_form_ff",
    "calc_beam_lf",
    "calc_cost",
    "calc_cost_per_unit",
    "calc_sale_per_unit",
}

# The labor card's header line for this assembly, and the switch beside it.
LABOR_DRIVER_KEYS = {
    "kind",
    "total_sf",
    "perm_edge_lf",
    "gb_form_ff",
    "pt_lb",
    "total_rebar_tons",
    "super_days",
    "super_weeks",
}


def test_the_totals_endpoint_carries_every_stat_card(client, section):
    body = client.get(f"/api/deck-levels/totals?section_id={section.id}").json()
    assert TOTALS_KEYS <= set(body), sorted(TOTALS_KEYS - set(body))


def test_the_grid_rows_carry_every_column(client, section):
    rows = client.get(f"/api/deck-levels?section_id={section.id}").json()
    assert rows, "the fixture builds two levels"
    assert ROW_KEYS <= set(rows[0]), sorted(ROW_KEYS - set(rows[0]))
    # The beams are nested on the row, because the grid shows a count and a
    # length and would otherwise need a second request per row.
    assert rows[0]["beams"] and "length_lf" in rows[0]["beams"][0]


def test_the_labor_card_can_describe_a_deck(client, section):
    body = client.get(f"/api/sections/{section.id}/labor").json()
    assert LABOR_DRIVER_KEYS <= set(body["drivers"]), sorted(
        LABOR_DRIVER_KEYS - set(body["drivers"])
    )
    # The `sub` badge and the switch both read this.
    assert all("subcontracted" in ln for ln in body["lines"])


def test_the_section_payload_carries_the_sub_labor_switch(client, section):
    body = client.get(f"/api/sections/{section.id}").json()
    assert body["labor_subcontracted"] is True


def test_the_forming_card_can_describe_a_deck(client, section):
    body = client.get(f"/api/sections/{section.id}/forming-materials").json()
    d = body["drivers"]
    for key in ("total_sf", "perimeter_lf", "form_percent", "form_waste"):
        assert key in d, key
    # An unpriced line has to reach the screen as one, not as a zero.
    assert "reshoring" in body["missing_prices"]


def test_the_money_cards_get_their_lines(client, section):
    """
    Concrete, steel and PT are the three stat cards on this page that show
    dollars — `app.js` reads `concrete`, `rebar` and `pt` off this payload.
    Until 2026-09-04 a deck came back with no lines at all and every card
    showed a quantity with nothing under it (audit P2 #3).
    """
    from decimal import Decimal

    r = client.get(f"/api/sections/{section.id}/material-costs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "cip_deck"
    assert {"concrete", "rebar", "pt"} <= {ln["key"] for ln in body["lines"]}
    # ...and they are the section's own money, not a second opinion.
    assert abs(Decimal(body["rounding"])) < Decimal("0.20")
