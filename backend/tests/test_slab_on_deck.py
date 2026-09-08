"""
Slab on deck (sql/075, 2026-09-08): the 09-SLAB ON DECK template as a kind on
the rebar-slab variant of the mono engine. Chad: "ok, lets do slab on deck".

No job has priced one, so each line is checked against the template's own
formula worked by hand in the fixture, and the total is held as a regression
golden whose parts are asserted to add up.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import load_stored_equipment, refresh_and_store_equipment
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.material_costs import section_material_costs
from app.services.recalc import recalc_section
from tests import slab_on_deck_fixture as sod

D = Decimal


def _build(db, estimate):
    section = sod.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    sod.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _lines(payload) -> dict:
    return {ln["code"]: ln for ln in payload["lines"]}


def _section(db, section_id) -> dict:
    return db.execute(text("SELECT unit, calc_total_cost, calc_total_tax, calc_total_sale, calc_quantity, calc_unpriced "
                           "FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}).mappings().one()


def _pour(db, section_id) -> dict:
    return db.execute(text("SELECT calc_concrete_cy, calc_total_rebar_lb, calc_support_rebar_lb, calc_sand_cy, "
                           "calc_poly_sf, calc_direct_cost, calc_allocated_cost, calc_equip_fuel, calc_tax, calc_cost "
                           "FROM mono_slabs WHERE section_id = :i"), {"i": str(section_id)}).mappings().one()


def test_the_templates_quantities(db, estimate):
    q = _pour(db, _build(db, estimate).id)
    assert D(str(q["calc_concrete_cy"])) == sod.CONCRETE_CY               # 157.037 CY
    assert D(str(q["calc_total_rebar_lb"])) == sod.STEEL_LB               # 17,635.2 lb
    assert D(str(q["calc_support_rebar_lb"])) == 0
    assert q["calc_sand_cy"] is None, "no sand on a deck"
    assert D(str(q["calc_poly_sf"])) == sod.SF * D("1.1"), "the barrier area carries the company poly waste"


def test_the_bar_is_the_pt_slab_item_and_the_labor_is_the_templates(db, estimate):
    section = _build(db, estimate)
    m = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert m["rebar"]["unit_cost"] == D("0.6000") and "PIERS" in (m["rebar"].get("detail") or m["rebar"].get("name") or "PIERS")
    labor = load_stored_labor(db, section.id)
    lines = _lines(labor)
    assert labor["drivers"]["super_days_are_typed"] is True and D(str(labor["drivers"]["super_days"])) == 10
    assert lines["grading"]["label"] == "SLAB PREP"
    assert D(str(lines["forming"]["ext_cost"])) == D("600.00")            # 12,000 x 0.05
    assert D(str(lines["grading"]["ext_cost"])) == D("1200.00")           # x 0.10
    assert D(str(lines["place_finish"]["ext_cost"])) == D("6000.00")      # x 0.50
    assert D(str(lines["wreck"]["ext_cost"])) == D("2400.00")             # x 0.20
    assert D(str(lines["tie_steel"]["qty"])) == sod.TIE_TONS
    assert D(str(lines["tie_steel"]["ext_cost"])) == (sod.TIE_TONS * D("350")).quantize(D("0.01"))
    assert D(str(labor["total_supervision_cost"])) == D("9750.00")        # 10 days x (425 + 250 + 100 + 200)


def test_the_equipment_is_the_templates(db, estimate):
    """Ten superintendent days rent fourteen; 8-20 days bill days/7 x 3."""
    section = _build(db, estimate)
    eq = _lines(load_stored_equipment(db, section.id))
    assert eq["mini_excavator"]["enabled"] is False and eq["skid_steer"]["enabled"] is False
    assert eq["skytrack"]["enabled"] is False
    assert eq["trencher"]["enabled"] is True and D(str(eq["trencher"]["ext_cost"])) == D("1950.00")   # 325 x 6
    assert D(str(eq["vault"]["ext_cost"])) == D("150.00") and D(str(eq["misc_equip"]["ext_cost"])) == D("330.00")
    assert D(str(eq["concrete_pump"]["ext_cost"])) == (sod.CONCRETE_CY * D("20")).quantize(D("0.01"))
    assert "demo" in eq and "engineering" not in eq
    assert D(str(eq["demo"]["rate"])) == D("1.75") and D(str(eq["demo"]["ext_cost"])) == 0
    assert D(str(eq["saw_cutting"]["days_qty"])) == 0, "the 09 tab has no joint formula — typed"
    assert D(str(eq["saw_cutting"]["rate"])) == D("0.35")


def test_the_lumber_block_is_the_templates(db, estimate):
    section = _build(db, estimate)
    f = _lines(load_stored_forming(db, section.id))
    assert D(str(f["2x6"]["qty"])) == 220                                 # 440 x 0.5
    assert D(str(f["2x4"]["qty"])) == 330                                 # 220 x 3 x 0.5
    assert D(str(f["2x10"]["qty"])) == 220                                # once around
    assert D(str(f["siding"]["qty"])) == 1 and D(str(f["stakes"]["qty"])) == 9
    assert (D(str(f["16p"]["qty"])), D(str(f["8p"]["qty"])), D(str(f["20p"]["qty"]))) == (2, 2, 2)
    assert abs(D(str(f["anchors"]["qty"])) - D("2.933")) <= D("0.001")
    assert D(str(f["chairs"]["qty"])) == 1 and D(str(f["tie_wire"]["qty"])) == D("0.8")
    assert D(str(f["cure"]["qty"])) == 1 and D(str(f["cure"]["unit_cost"])) == D("225.00")
    assert D(str(f["haul_off"]["qty"])) == (sod.CONCRETE_CY / D("300")).quantize(D("0.001"))
    assert D(str(f["haul_off"]["unit_cost"])) == D("500.00") and f["haul_off"]["taxable"] is False
    assert D(str(f["accessories"]["qty"])) == sod.STEEL_LB


def test_the_total_is_the_sum_of_its_parts(db, estimate):
    section = _build(db, estimate)
    row = _section(db, section.id)
    q = _pour(db, section.id)
    assert row["unit"] == "SF" and D(str(row["calc_quantity"])) == sod.SF
    parts = D(str(q["calc_direct_cost"])) + D(str(q["calc_allocated_cost"])) + D(str(q["calc_equip_fuel"])) + D(str(q["calc_tax"]))
    assert D(str(q["calc_cost"])) == parts.quantize(D("0.01")) == D(str(row["calc_total_cost"]))
    labor = load_stored_labor(db, section.id)
    eq = load_stored_equipment(db, section.id)
    fm = load_stored_forming(db, section.id)
    allocated = D(str(labor["total_cost"])) + D(str(eq["total_cost"])) + D(str(fm["total_ext_cost"]))
    assert D(str(q["calc_allocated_cost"])) == allocated.quantize(D("0.01"))
    assert D(str(q["calc_equip_fuel"])) == (D(str(eq["total_equipment_cost"])) * D("0.5")).quantize(D("0.01"))
    assert D(str(row["calc_total_cost"])) == sod.GOLDEN_COST
    assert not [x for x in row["calc_unpriced"] if "mobilization" not in x], row["calc_unpriced"]


def test_the_kind_is_offered_and_a_pour_saves(client, db, estimate):
    assert "slab_on_deck" in client.get("/api/sections/meta/kinds").json()
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "slab_on_deck", "name": "Deck slab"})
    assert r.status_code == 201 and r.json()["unit"] == "SF", r.text
    sid = r.json()["id"]
    mix = client.get("/api/mix-designs").json()[0]["id"]
    r = client.post("/api/mono-slabs", json={
        "section_id": sid, "description": "L2", "square_footage": "1000", "thickness_in": "4",
        "perimeter_edge_lf": "130", "mix_design_id": mix, "post_tension": False, "wire_mesh": False,
        "slab_bar_size": 4, "slab_bar_spacing_in": "12",
    })
    assert r.status_code == 201, r.text
    rates = {x["key"] for x in client.get(f"/api/sections/{sid}/rates").json()["rows"]}
    assert {"labor_grading_sf", "demo_lf", "saw_cutting_lf", "labor_tie_steel_free_lb_per_sf"} <= rates
    codes = {ln["code"] for ln in client.get(f"/api/sections/{sid}/equipment").json()["lines"]}
    assert {"demo", "trencher", "saw_cutting"} <= codes and "engineering" not in codes
