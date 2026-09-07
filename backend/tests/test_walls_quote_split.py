"""
The wall/footing split follows a rebar quote (audit 2026-09-04, P3 — batch 1, 2026-09-06).

`walls._rebar_price` said "a rebar quote included" and read the catalog. The
section total was right either way — costing prices the steel from the quote
— but the split of each row into its wall half and its footing half priced
the footing's bar at the catalog and let the wall absorb the difference. Under
a unit quote the footing was dear by (catalog − quote) per pound of footing
steel; under a lump it never saw the lump at all.

Now the split reads the quote: a unit quote as $/lb, a lump as $/lb across the
section's steel — the same weights costing spreads the lump by — and the two
halves still sum to the row to the cent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.estimate_section import EstimateSection
from app.services.costing import tax_rate_for
from tests import walls_fixture as wf

D = Decimal
CATALOG = wf.MATERIAL_PRICES["REBAR GRADE BEAM"]  # what walls bar costs without a quote


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _rows(client, sid):
    return {r["id"]: r for r in client.get(f"/api/wall-runs?section_id={sid}").json()}


def _quote(client, sid, amount, unit):
    r = client.put(f"/api/sections/{sid}/quotes/rebar", json={"amount": str(amount), "unit": unit})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/sections/{sid}/recalc").status_code == 200


def test_the_halves_always_sum_to_the_row(client, db, estimate):
    section = wf.build(db, estimate)
    assert client.post(f"/api/sections/{section.id}/recalc").status_code == 200
    for kind_of_quote in (("0.45", "LB"), ("12000", "LS")):
        _quote(client, section.id, *kind_of_quote)
        for r in _rows(client, section.id).values():
            assert D(r["calc_wall_cost"]) + D(r["calc_footing_cost"]) == D(r["calc_cost"]), r["label"]


def test_a_unit_quote_reprices_the_footing_steel_by_the_pound(client, db, estimate):
    section = wf.build(db, estimate)
    assert client.post(f"/api/sections/{section.id}/recalc").status_code == 200
    before = _rows(client, section.id)
    taxed = D("1") + tax_rate_for(db, db.get(EstimateSection, section.id))

    _quote(client, section.id, "0.45", "LB")  # a dime under the catalog's $0.55
    after = _rows(client, section.id)
    for rid, r in after.items():
        ftg_lb = D(r["calc_footing_rebar_lb"])
        expected_drop = (ftg_lb * (CATALOG - D("0.45")) * taxed).quantize(D("0.01"))
        drop = D(before[rid]["calc_footing_cost"]) - D(r["calc_footing_cost"])
        assert abs(drop - expected_drop) <= D("0.02"), (r["label"], drop, expected_drop)


def test_a_lump_quote_reaches_the_footing_as_its_share_by_the_pound(client, db, estimate):
    section = wf.build(db, estimate)
    assert client.post(f"/api/sections/{section.id}/recalc").status_code == 200
    before = _rows(client, section.id)
    taxed = D("1") + tax_rate_for(db, db.get(EstimateSection, section.id))
    total_lb = sum(D(r["calc_total_rebar_lb"]) for r in before.values())

    lump = D("12000")
    _quote(client, section.id, lump, "LS")
    effective = lump / total_lb  # $/lb the lump comes to across the section
    after = _rows(client, section.id)
    for rid, r in after.items():
        ftg_lb = D(r["calc_footing_rebar_lb"])
        expected_delta = (ftg_lb * (effective - CATALOG) * taxed).quantize(D("0.01"))
        delta = D(r["calc_footing_cost"]) - D(before[rid]["calc_footing_cost"])
        assert abs(delta - expected_delta) <= D("0.03"), (r["label"], delta, expected_delta)
