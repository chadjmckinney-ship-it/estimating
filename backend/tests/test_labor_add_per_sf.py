"""
The add $/SF on every pour-shaped row (2026-09-10).

Chad, 2026-09-10: "on the LBJ workbook, there is a column for most items of
a cost added per sf" — the slab tab's LABOR ADD /SF (column C, CP = C × SF,
summed on the LABOR ADD line), the paving tab's Paving Add $$/SF, the
sidewalks tab's Cost Adder. Paving has carried it since sql/036; now a mono
slab, a rebar slab and a walk do too, on the same field.

Pinned: the line rides the rows (square feet times the building count
times the rate, at $1 a lump), a row without one contributes nothing, the
section's cost moves by exactly the add, the API takes it on a pour and the
line follows, and a typed total still pins the line.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text

from app.models.estimate_labor import EstimateLaborLine
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs
from app.services.costing import refresh_pour_costs
from app.services.labor import calc_labor_materials, get_or_refresh_labor, refresh_and_store_labor, update_labor_line
from app.services.price_book import pull_prices
from tests import sidewalks_fixture as swf

D = Decimal


def _line(lines, code):
    return next(ln for ln in lines if ln["code"] == code)


def test_a_slabs_labor_add_rides_the_pours_add_per_sf(db, estimate, section, make_pour):
    pull_prices(db, estimate.id)
    plain = make_pour(description="No add")
    lines = calc_labor_materials(db, section.id)["lines"]
    add = _line(lines, "labor_add")
    assert (add["label"], add["unit"], D(str(add["rate"])), D(str(add["qty"])), D(str(add["ext_cost"]))) == ("LABOR ADD", "LS", D("1"), D("0"), D("0"))
    assert "add $/SF" in (add["notes"] or "")

    # Three buildings of a 10,000 SF pour at $0.50: 15,000 on the line, at $1 a lump.
    make_pour(description="With add", qty=3, paving_add_per_sf=D("0.50"))
    lines = calc_labor_materials(db, section.id)["lines"]
    add = _line(lines, "labor_add")
    assert D(str(add["qty"])) == D("15000") and D(str(add["ext_cost"])) == D("15000.00") and add["notes"] is None
    assert D(str(_line(lines, "forming")["qty"])) == D("40000")      # the plain pour and three of the other

    # The section's cost moves by the add and nothing else.
    get_or_refresh_labor(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    before = D(str(section.calc_total_cost))
    plain.paving_add_per_sf = D("0.25")
    db.flush()
    refresh_mono_slab_calcs(db, plain, section)
    refresh_and_store_labor(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    assert D(str(section.calc_total_cost)) - before == D("2500.00")
    stored = db.scalars(select(EstimateLaborLine).where(EstimateLaborLine.section_id == section.id, EstimateLaborLine.code == "labor_add")).one()
    assert stored.qty == D("17500.0000") and stored.ext_cost == D("17500.00") and stored.is_manual is False

    # A typed total still pins the line — the old manual lump is not gone.
    update_labor_line(db, section.id, "labor_add", qty=D("20000"), mark_manual=True)
    db.expire_all()
    stored = db.scalars(select(EstimateLaborLine).where(EstimateLaborLine.section_id == section.id, EstimateLaborLine.code == "labor_add")).one()
    assert stored.qty == D("20000.0000") and stored.is_manual is True


def test_the_screen_sets_it_on_a_pour_and_the_line_follows(client, db, estimate, section, make_pour):
    pull_prices(db, estimate.id)
    pour = make_pour(description="Pour A")
    client.get(f"/api/sections/{section.id}/labor")   # the set exists, the way opening the section makes it
    r = client.patch(f"/api/mono-slabs/{pour.id}", json={"paving_add_per_sf": 0.75})
    assert r.status_code == 200, r.text
    assert D(str(r.json()["paving_add_per_sf"])) == D("0.75")
    labor = client.get(f"/api/sections/{section.id}/labor").json()
    add = next(ln for ln in labor["lines"] if ln["code"] == "labor_add")
    assert D(str(add["qty"])) == D("7500") and D(str(add["ext_cost"])) == D("7500.00")
    # Blank takes it off again.
    assert client.patch(f"/api/mono-slabs/{pour.id}", json={"paving_add_per_sf": None}).status_code == 200
    labor = client.get(f"/api/sections/{section.id}/labor").json()
    assert D(str(next(ln for ln in labor["lines"] if ln["code"] == "labor_add")["qty"])) == 0


def test_a_walks_cost_adder_is_a_labor_adjustment(db, estimate):
    section = swf.build(db, estimate)
    lines = calc_labor_materials(db, section.id)["lines"]
    adj = _line(lines, "labor_add")
    assert adj["label"] == "LABOR ADJUSTMENT" and D(str(adj["qty"])) == 0
    walk = db.scalars(select(MonoSlab).where(MonoSlab.section_id == section.id).order_by(MonoSlab.sort_order)).first()
    walk.paving_add_per_sf = D("0.30")
    db.flush()
    refresh_mono_slab_calcs(db, walk, section)
    lines = calc_labor_materials(db, section.id)["lines"]
    adj = _line(lines, "labor_add")
    assert D(str(adj["qty"])) == (D(str(walk.square_footage)) * D("0.30")).quantize(D("0.0001"))
    assert D(str(adj["ext_cost"])) == (D(str(walk.square_footage)) * D("0.30")).quantize(D("0.01"))
    # The other walks carry nothing and the per-SF lines are untouched.
    assert D(str(_line(lines, "forming")["qty"])) == D(str(db.execute(
        text("SELECT sum(square_footage * qty) FROM mono_slabs WHERE section_id = :s"), {"s": str(section.id)}).scalar()))
