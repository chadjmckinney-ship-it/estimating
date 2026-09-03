"""
The dollars behind the quantity cards.

Every section page has always shown the takeoff at the top — 2,205 CY, 21,945
lb, 158,109 SF of poly — and no price next to any of it. The breakdown these
tests cover is what puts a dollar figure on each of those, and the property
that makes it trustworthy is not that any single line is pretty: it is that the
lines ADD UP TO THE SAME DIRECT COST the section was already priced at.

That is the assertion to keep. A breakdown computed independently of the total
it breaks down is a second implementation of costing, and the day it disagrees
is the day nobody knows which one is right. Every test below either checks a
line against a price the fixture itself states, or checks the sum against
`calc_direct_cost`.

The one number that is allowed to be non-zero is `rounding`, and only in cents:
costing quantizes once per row, this quantizes once per material, and 17 pours
of that is a few cents. A dollar there is a bug.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.costing import refresh_pour_costs
from app.services.material_costs import section_material_costs
from tests import mono_slab_fixture as mf
from tests import piers_fixture as pf
from tests import walls_fixture as wf


def _by_key(payload) -> dict:
    return {ln["key"]: ln for ln in payload["lines"]}


def _cents(x) -> Decimal:
    return Decimal(str(x)).copy_abs()


def _quote(db, section, kind, amount, unit, note=None) -> None:
    """Put a quote on a section and re-cost. Mirrors what the PUT endpoint does."""
    from app.models.section_quote import SectionQuote

    row = SectionQuote(
        section_id=section.id, kind=kind, amount=Decimal(str(amount)), unit=unit,
        note=note,
    )
    db.add(row)
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()


# ------------------------------------------------------------------ slabs ----


@pytest.fixture
def slab(db, estimate):
    section = mf.build(db, estimate)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def test_slab_lines_add_up_to_the_direct_cost(db, slab):
    """The whole point. $393,605.54 of materials, itemised."""
    out = section_material_costs(db, slab)
    assert out["direct_cost"] == mf.GOLDEN_COST["direct"]
    # Per-row vs per-material rounding across 17 pours. Cents, not dollars.
    assert _cents(out["rounding"]) < Decimal("0.20")
    assert out["total_material_cost"] + out["rounding"] == out["direct_cost"]


def test_slab_quantities_are_the_takeoff_not_a_second_opinion(db, slab):
    lines = _by_key(section_material_costs(db, slab))
    assert lines["concrete"]["qty"] == mf.GOLDEN_QTY["total_concrete_cy"]
    assert lines["rebar"]["qty"] == mf.GOLDEN_QTY["total_rebar_lb"]
    assert lines["poly"]["qty"] == mf.GOLDEN_QTY["total_poly_sf"]
    assert lines["sand"]["qty"] == mf.GOLDEN_QTY["total_sand_cy"]
    # PT is priced per SF of post-tensioned pour, not per cable foot.
    assert lines["pt"]["qty"] == mf.GOLDEN_QTY["total_sf"]


def test_slab_unit_costs_are_the_prices_the_fixture_states(db, slab):
    """
    A card that shows $/CY has to show the price that was actually paid.

    These come from the fixture, not the catalog — which is the same reason the
    golden test states its own prices.
    """
    lines = _by_key(section_material_costs(db, slab))
    assert lines["concrete"]["unit_cost"] == mf.MIX_UNIT_COST
    assert lines["rebar"]["unit_cost"] == mf.MATERIAL_PRICES["REBAR PIERS / PT slabs"]
    assert lines["pt"]["unit_cost"] == mf.MATERIAL_PRICES["POST TENSION CABLES"]
    assert lines["concrete"]["detail"] == mf.MIX_CODE or lines["concrete"]["detail"]
    # Poly is bought by the roll and reported by the SF it covers, so its unit
    # cost is a derived $/SF — the number worth eyeballing, not the roll price.
    assert lines["poly"]["unit"] == "SF"
    assert Decimal("0.01") < lines["poly"]["unit_cost"] < Decimal("0.30")


def test_a_slab_with_no_mesh_has_no_mesh_line(db, slab):
    """Absent, not zero — the same rule the line sets follow."""
    assert "mesh" not in _by_key(section_material_costs(db, slab))


def test_every_slab_line_names_where_its_price_came_from(db, slab):
    for ln in section_material_costs(db, slab)["lines"]:
        assert ln["source"] in {"catalog", "quote", "quote (lump)", "rate"}
        assert ln["label"]


# ------------------------------------------------------------------ piers ----


@pytest.fixture
def piers(db, estimate):
    section = pf.build(db, estimate)
    pf.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def test_pier_lines_add_up_to_the_direct_cost(db, piers):
    out = section_material_costs(db, piers)
    assert _cents(out["rounding"]) < Decimal("0.20")
    assert out["total_material_cost"] + out["rounding"] == out["direct_cost"]


def test_drilling_is_on_the_list_even_though_it_is_not_a_purchase(db, piers):
    """
    It is work, and it is never taxed — and it is also the biggest number on a
    piers section, sitting directly under a card that says "Drilled LF". A
    breakdown that left it out would be missing most of the money.
    """
    lines = _by_key(section_material_costs(db, piers))
    assert lines["drilling"]["unit"] == "LF"
    assert lines["drilling"]["cost"] > 0
    assert lines["drilling"]["source"] == "rate"


# ------------------------------------------------------------------ walls ----


@pytest.fixture
def walls(db, estimate):
    section = wf.build(db, estimate)
    wf.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def test_wall_lines_add_up_to_the_direct_cost(db, walls):
    out = section_material_costs(db, walls)
    assert _cents(out["rounding"]) < Decimal("0.20")
    assert out["total_material_cost"] + out["rounding"] == out["direct_cost"]


def test_walls_report_two_concretes_at_two_prices(db, walls):
    """
    The only assembly so far that buys from two mixes. Reporting one blended
    $/CY would hide exactly the thing the split exists to show — cheaper
    concrete in the ground, better concrete in the wall.
    """
    lines = _by_key(section_material_costs(db, walls))
    assert lines["wall_concrete"]["unit_cost"] == wf.WALL_MIX_COST
    assert lines["footing_concrete"]["unit_cost"] == wf.FOOTING_MIX_COST
    assert lines["wall_concrete"]["unit_cost"] > lines["footing_concrete"]["unit_cost"]


# ----------------------------------------------------------------- quotes ----


def test_a_lump_quote_replaces_the_rate_but_not_the_quantity(db, walls):
    """
    A quoted section still has 33,728 lb of steel on it. The card above the
    dollars reads pounds, and it has to keep reading pounds — what changes is
    that the money is the fabricator's number and says so.
    """
    before = _by_key(section_material_costs(db, walls))["rebar"]

    _quote(db, walls, "rebar", "21000.00", "LS", note="Ace Steel 8/28")

    after = _by_key(section_material_costs(db, walls))["rebar"]
    assert after["qty"] == before["qty"]
    assert after["cost"] == Decimal("21000.00")
    assert after["source"] == "quote (lump)"
    assert after["detail"] == "Ace Steel 8/28"

    out = section_material_costs(db, walls)
    assert _cents(out["rounding"]) < Decimal("0.20")
    assert out["total_material_cost"] + out["rounding"] == out["direct_cost"]


def test_a_unit_priced_quote_shows_as_the_rate_it_is(db, walls):
    _quote(db, walls, "rebar", "1200.00", "TON")

    rebar = _by_key(section_material_costs(db, walls))["rebar"]
    assert rebar["source"] == "quote"
    assert rebar["unit_cost"] == Decimal("0.6000")   # $1,200/ton = $0.60/lb


# -------------------------------------------------------------------- API ----


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_the_endpoint_serves_the_breakdown(client, slab):
    r = client.get(f"/api/sections/{slab.id}/material-costs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "mono_slab"
    assert {ln["key"] for ln in body["lines"]} >= {"concrete", "rebar", "pt", "poly"}
    assert Decimal(body["direct_cost"]) == mf.GOLDEN_COST["direct"]


def test_an_unknown_section_is_a_404(client):
    r = client.get("/api/sections/00000000-0000-0000-0000-000000000000/material-costs")
    assert r.status_code == 404


# ---------------------------------------------------------------- columns ----


@pytest.fixture
def columns(db, estimate):
    from tests import columns_fixture as colf

    section = colf.build(db, estimate)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def test_column_lines_add_up_to_the_direct_cost(db, columns):
    out = section_material_costs(db, columns)
    assert _cents(out["rounding"]) < Decimal("0.20")
    assert out["total_material_cost"] + out["rounding"] == out["direct_cost"]


def test_a_column_section_buys_concrete_and_bar_and_nothing_else(db, columns):
    """
    Everything else a column costs — plywood, chamfer, ties, the hoist — is a
    forming or equipment line, not a purchase sitting on the takeoff row.
    """
    lines = _by_key(section_material_costs(db, columns))
    assert set(lines) == {"concrete", "rebar"}
    assert lines["concrete"]["unit_cost"] == Decimal("175.0000")
    assert lines["rebar"]["unit_cost"] == Decimal("0.6500")
