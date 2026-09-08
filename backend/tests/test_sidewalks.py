"""
Sidewalks (sql/076, 2026-09-08): the SIDEWALKS tab Chad populated, as the
sidewalk kind's own line sets on the paving-family engine.
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
from tests import sidewalks_fixture as sw

D = Decimal


def _build(db, estimate):
    section = sw.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _lines(payload) -> dict:
    return {ln["code"]: ln for ln in payload["lines"]}


def _section(db, section_id) -> dict:
    return db.execute(text("SELECT unit, calc_total_cost, calc_total_tax, calc_total_sale, calc_quantity, "
                           "calc_cost_per_unit, calc_sale_per_unit, calc_unpriced FROM estimate_sections WHERE id = :i"),
                      {"i": str(section_id)}).mappings().one()


def _sums(db, section_id) -> dict:
    return db.execute(text("SELECT sum(square_footage) AS sf, sum(calc_concrete_cy) AS cy, "
                           "sum(calc_stair_concrete_cy) AS stairs, sum(calc_total_rebar_lb) AS lb, "
                           "sum(calc_edge_rebar_lb) AS edge_lb, sum(calc_sand_cy) AS sand, sum(calc_poly_sf) AS poly "
                           "FROM mono_slabs WHERE section_id = :i"), {"i": str(section_id)}).mappings().one()


# ----------------------------------------------------------- the takeoff --


def test_the_tabs_quantities(db, estimate):
    q = _sums(db, _build(db, estimate).id)
    assert D(str(q["sf"])) == sw.SHEET["total_sf"]
    assert abs(D(str(q["cy"])) - sw.SHEET["concrete_cy"]) <= D("0.001")
    assert D(str(q["stairs"])) == sw.SHEET["stair_cy"]                       # 50 x 6 x 24 / 3888 x 1.08
    assert abs(D(str(q["lb"])) - sw.SHEET["steel_lb"]) / sw.SHEET["steel_lb"] < D("0.001")
    assert D(str(q["edge_lb"])) == 0, "no thickened edge on these three walks"
    assert abs(D(str(q["sand"])) - sw.SHEET["sand_cy"]) <= D("0.001")       # with the tab's 5%, per pour
    assert D(str(q["poly"])) == 0, "no poly line on the SIDEWALKS tab"


def test_a_thickened_edge_carries_its_width_and_its_two_bars(db, estimate):
    from app.models.mono_slab import MonoSlab
    from app.services.calc import refresh_mono_slab_calcs

    section = sw.build(db, estimate)
    slab = db.query(MonoSlab).filter(MonoSlab.section_id == section.id).order_by(MonoSlab.sort_order).first()
    slab.thick_edge_lf = D("100")
    refresh_mono_slab_calcs(db, slab, section)
    # V10: 100 x 1.8 x 0.18 / 27 x 1.08; U10: 100 x 2 bars x 0.376 lb/ft, outside the waste
    assert D(str(slab.calc_edge_concrete_cy)) == (D("100") * D("1.8") * D("0.18") / D("27") * D("1.08")).quantize(D("0.0001"))
    assert D(str(slab.calc_edge_rebar_lb)) == D("75.200")


# --------------------------------------------------------------- labor --


def test_the_labor_and_supervision_are_the_tabs(db, estimate):
    section = _build(db, estimate)
    labor = load_stored_labor(db, section.id)
    lines = _lines(labor)
    assert D(str(lines["forming"]["ext_cost"])) == D("70131.25")            # 40,075 x 1.75
    assert D(str(lines["place_finish"]["ext_cost"])) == D("40075.00")
    assert D(str(lines["wreck"]["ext_cost"])) == D("10018.75")
    assert D(str(lines["stair_treads"]["qty"])) == 50 and D(str(lines["stair_treads"]["ext_cost"])) == D("100.00")
    assert D(str(lines["thick_edge"]["ext_cost"])) == 0 and D(str(lines["ada_ramps"]["rate"])) == D("400")
    assert "tie_steel" not in lines and "curb" not in lines and "grading" not in lines
    assert D(str(labor["total_labor_cost"])) == sw.SHEET["labor"]
    # D57: CY / 10 x 1.5 + 5 — on the app's CY, a hair over the tab's 536.3333
    assert abs(D(str(labor["drivers"]["super_days"])) - sw.SHEET["super_days"]) < D("0.01")
    assert D(str(lines["superintendent"]["rate"])) == D("390") and D(str(lines["foreman"]["qty"])) == 0
    assert D(str(lines["expense"]["qty"])) == D(str(lines["superintendent"]["qty"]))
    assert D(str(lines["pm"]["qty"])) == 0, "no project manager on this tab"
    assert "CY" in lines["superintendent"]["formula"]


# ----------------------------------------------------------- equipment --


def test_the_equipment_and_the_finishes_are_the_tabs(db, estimate):
    section = _build(db, estimate)
    eq = _lines(load_stored_equipment(db, section.id))
    # 85.45 days rent 150 (7 + 143); over 29 days bill days/30 x 9: 45 units x 350
    assert D(str(eq["bobcat"]["days_qty"])) == 150 and D(str(eq["bobcat"]["ext_cost"])) == D("15750.00")
    assert D(str(eq["misc_equip"]["ext_cost"])) == D("1125.00")            # 45 x 25
    for code in ("backhoe", "trencher", "light_tower"):
        assert eq[code]["enabled"] is False, code
    assert D(str(eq["stamping"]["days_qty"])) == 7575 and D(str(eq["stamping"]["ext_cost"])) == D("26512.50")
    assert abs(D(str(eq["integral_color"]["days_qty"])) - D("101")) < D("0.01")
    assert abs(D(str(eq["integral_color"]["ext_cost"])) - D("10100.00")) < D("1")
    assert D(str(eq["acid_etch"]["ext_cost"])) == D("40000.00")
    assert D(str(eq["joint_construction"]["days_qty"])) == 2672 and D(str(eq["joint_control"]["days_qty"])) == 13358
    assert D(str(eq["joint_construction"]["ext_cost"])) == 0 and D(str(eq["saw_cutting"]["ext_cost"])) == 0
    assert D(str(eq["concrete_pump"]["ext_cost"])) == 0 and D(str(eq["barricades"]["ext_cost"])) == 0


# ------------------------------------------------------------- forming --


def test_the_lumber_block_runs_off_square_feet(db, estimate):
    section = _build(db, estimate)
    f = _lines(load_stored_forming(db, section.id))
    assert D(str(f["2x4"]["qty"])) == D("10018.75")                          # SF / 4
    assert D(str(f["stakes"]["qty"])) == D("100.188")                        # SF / 400, to three places
    assert (D(str(f["16p"]["qty"])), D(str(f["8p"]["qty"]))) == (7, 9)
    assert D(str(f["rw4"]["qty"])) == 2672 and D(str(f["rw8"]["qty"])) == 0  # expansion joints, all walks 4"
    assert D(str(f["tack_strip"]["qty"])) == 2672 and D(str(f["tack_strip"]["unit_cost"])) == D("0.15")
    assert D(str(f["smooth_dowels"]["qty"])) == 1782                         # 2,672 x 12 / 18
    assert abs(D(str(f["tie_wire"]["qty"])) - D("2.672")) <= D("0.001")
    assert abs(D(str(f["cure"]["qty"])) - D("2.505")) <= D("0.001")         # SF / 16,000
    assert D(str(f["cure"]["unit_cost"])) == D("540.00")
    for code in ("2x6", "2x8", "2x10", "siding", "ply", "chairs", "keyway", "chamfer"):
        assert D(str(f[code]["qty"])) == 0, code
    assert load_stored_forming(db, section.id)["missing_prices"] == []


# ------------------------------------------------------------ the money --


def test_the_material_list(db, estimate):
    section = _build(db, estimate)
    m = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert abs(D(str(m["concrete"]["cost"])) - D("83131.67")) < D("0.05")    # 536.33 CY x $155
    assert abs(D(str(m["sand"]["cost"])) - D("6493.64")) <= D("0.01")       # 259.7454 CY x $25, per pour
    assert m["rebar"]["unit_cost"] == D("0.6500")
    assert "poly" not in m or D(str(m["poly"]["cost"])) == 0


def test_the_total_and_every_cent_of_the_variance(db, estimate):
    section = _build(db, estimate)
    row = _section(db, section.id)
    assert row["unit"] == "SF" and D(str(row["calc_quantity"])) == sw.SHEET["total_sf"]
    assert D(str(row["calc_total_cost"])) == sw.GOLDEN_COST
    pieces = (
        + D("515.26")   # accessories at the catalog's $0.04, not the tab's $0.02, taxed
        + D("655.31")   # fuel and tax on MISCELLANEOUS, which the sheet exempts (1,125 x 0.5825)
        + D("402.83")   # tax on the tack strip, tie wire, cure and dowels the tab leaves untaxed
        + D("11.77")    # 17 lb of catalog bar weight, taxed
        + D("0.17")     # stakes and cure quantities kept to three places
    )
    named = sw.SHEET["total_cost"].quantize(D("0.01")) + pieces
    assert abs(named - sw.GOLDEN_COST) <= D("0.03"), named - sw.GOLDEN_COST
    # Sale: cost x (1 + 20% margin + the Summary's 3% contingency), per SF beside it.
    assert D(str(row["calc_total_sale"])) == (sw.GOLDEN_COST * D("1.23")).quantize(D("0.01"))
    assert not [x for x in row["calc_unpriced"] if "mobilization" not in x], row["calc_unpriced"]


# ----------------------------------------------------------------- API --


def test_the_grid_saves_a_walk_with_its_finishes_and_stairs(client, db, estimate):
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "sidewalk", "name": "Walks"})
    assert r.status_code == 201 and r.json()["unit"] == "SF", r.text
    sid = r.json()["id"]
    mix = client.get("/api/mix-designs").json()[0]["id"]
    r = client.post("/api/mono-slabs", json={
        "section_id": sid, "description": "City walk", "square_footage": "1000", "thickness_in": "4",
        "sand_thickness_in": "2", "mix_design_id": mix, "post_tension": False, "wire_mesh": False,
        "slab_bar_size": 3, "slab_bar_spacing_in": "18", "stamped": True, "integral_color": True,
        "stair_tread_lf": "20", "stair_tread_rise_in": "6", "stair_tread_run_in": "12", "thick_edge_lf": "40",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["stamped"] is True and D(body["calc_stair_concrete_cy"]) > 0 and D(body["calc_edge_rebar_lb"]) > 0
    t = client.get(f"/api/mono-slabs/totals?section_id={sid}").json()
    assert D(t["total_stamped_sf"]) == 1000 and D(t["total_stair_tread_lf"]) == 20 and D(t["total_thick_edge_lf"]) == 40
    rates = {x["key"] for x in client.get(f"/api/sections/{sid}/rates").json()["rows"]}
    assert {"labor_thick_edge_lf", "labor_stair_tread_lf", "labor_ada_ramp_ea", "integral_color_cy", "acid_etch_sf"} <= rates
    assert "labor_curb_lf" not in rates and "labor_grading_sf" not in rates
    codes = {ln["code"] for ln in client.get(f"/api/sections/{sid}/equipment").json()["lines"]}
    assert {"stamping", "integral_color", "acid_etch", "joint_construction", "bobcat"} <= codes
