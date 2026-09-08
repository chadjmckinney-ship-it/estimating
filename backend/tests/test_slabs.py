"""
Slabs (sql/074, 2026-09-07): the Pearl Landing Podium 05-Slabs tab as a kind
on the mono-slab engine. Chad: "ok, lets do slabs".
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
from tests import slabs_fixture as sf

D = Decimal


def _build(db, estimate):
    section = sf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    sf.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _cost(db, section_id) -> Decimal:
    return D(str(db.scalar(text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"), {"i": str(section_id)})))


def _lines(payload) -> dict:
    return {ln["code"]: ln for ln in payload["lines"]}


def _sums(db, section_id) -> dict:
    return db.execute(text("SELECT sum(square_footage) AS sf, sum(calc_concrete_cy) AS cy, "
                           "sum(calc_total_rebar_lb) AS lb, sum(calc_sand_cy) AS sand, sum(calc_poly_sf) AS poly, "
                           "sum(calc_support_rebar_lb) AS support FROM mono_slabs WHERE section_id = :i"),
                      {"i": str(section_id)}).mappings().one()


# ----------------------------------------------------------- the takeoff --


def test_the_tabs_quantities(db, estimate):
    q = _sums(db, _build(db, estimate).id)
    assert D(str(q["sf"])) == sf.SHEET["total_sf"]
    assert abs(D(str(q["cy"])) - sf.SHEET["concrete_cy"]) <= D("0.001")
    # #3 at 12" each way with the lap: the catalog's 0.376 lb/ft against the
    # tab's 0.3757 — a tenth of a percent.
    assert abs(D(str(q["lb"])) - sf.SHEET["steel_lb"]) / sf.SHEET["steel_lb"] < D("0.001")
    assert D(str(q["support"])) == 0, "no support-steel allowance on this tab"
    assert D(str(q["sand"])) == sf.SHEET["sand_cy"], "sand without waste (K73 is blank)"
    assert D(str(q["poly"])) == sf.SHEET["total_sf"], "the barrier covers the slab; no beams to wrap"


def test_the_superintendent_is_typed(db, estimate):
    section = _build(db, estimate)
    labor = load_stored_labor(db, section.id)
    assert labor["drivers"]["super_days_are_typed"] is True
    assert D(str(labor["drivers"]["super_days"])) == 20
    lines = _lines(labor)
    assert D(str(lines["superintendent"]["ext_cost"])) == D("8500.00")
    assert D(str(lines["pm"]["ext_cost"])) == D("4000.00")
    assert D(str(labor["total_supervision_cost"])) == sf.SHEET["supervision"]


# --------------------------------------------------------------- labor --


def test_the_labor_is_the_tabs(db, estimate):
    section = _build(db, estimate)
    labor = _lines(load_stored_labor(db, section.id))
    assert D(str(labor["forming"]["ext_cost"])) == D("14130.50")        # 56,522 x 0.25
    assert D(str(labor["grading"]["ext_cost"])) == D("28261.00")        # x 0.50
    assert D(str(labor["place_finish"]["ext_cost"])) == D("28261.00")   # x 0.50
    assert D(str(labor["wreck"]["ext_cost"])) == D("11304.40")          # x 0.20
    # The first 0.35 lb/SF is carried (U10): (steel - 56,522 x 0.35) / 2000 tons
    # at $350, on the app's own catalog-weight pounds.
    lb = D(str(_sums(db, section.id)["lb"]))
    tons = ((lb - sf.SHEET["total_sf"] * D("0.35")) / D("2000")).quantize(D("0.0001"))
    assert D(str(labor["tie_steel"]["qty"])) == tons
    assert D(str(labor["tie_steel"]["ext_cost"])) == (tons * D("350")).quantize(D("0.01"))
    assert abs(tons - sf.SHEET["tie_steel_tons"]) < D("0.02")
    assert D(str(labor["excavation"]["ext_cost"])) == 0 and D(str(labor["hold_downs"]["ext_cost"])) == 0


# ----------------------------------------------------------- equipment --


def test_the_equipment_is_the_tabs(db, estimate):
    """Twenty superintendent days rent thirty; thirty days bill nine units (E97, O97)."""
    section = _build(db, estimate)
    eq = _lines(load_stored_equipment(db, section.id))
    assert D(str(eq["mini_excavator"]["days_qty"])) == 30 and D(str(eq["mini_excavator"]["ext_cost"])) == D("4275.00")
    assert D(str(eq["vault"]["ext_cost"])) == D("225.00")               # 25 x 9
    assert D(str(eq["misc_equip"]["ext_cost"])) == D("495.00")          # 55 x 9
    assert eq["trencher"]["enabled"] is False and eq["skid_steer"]["enabled"] is False
    assert eq["skytrack"]["enabled"] is False
    assert D(str(eq["saw_cutting"]["days_qty"])) == D("5652.2") and D(str(eq["saw_cutting"]["ext_cost"])) == D("3108.71")
    assert eq["saw_joint_sealant"]["enabled"] is False and D(str(eq["saw_joint_sealant"]["ext_cost"])) == 0
    assert D(str(eq["concrete_pump"]["ext_cost"])) == D("9939.95")      # 993.9954 CY x $10
    assert D(str(eq["haul_off"]["ext_cost"])) == 0


# ------------------------------------------------------------- forming --


def test_the_lumber_block_is_the_tabs(db, estimate):
    section = _build(db, estimate)
    f = _lines(load_stored_forming(db, section.id))
    assert D(str(f["2x6"]["qty"])) == 815                                # perimeter x form% 1
    assert D(str(f["2x4"]["qty"])) == 2445                               # 2x6 x 3 + drops
    assert D(str(f["2x10"]["qty"])) == 815, "once around, not twice — the tab's V71"
    assert D(str(f["siding"]["qty"])) == 2 and D(str(f["stakes"]["qty"])) == 33
    assert (D(str(f["16p"]["qty"])), D(str(f["8p"]["qty"])), D(str(f["20p"]["qty"]))) == (3, 3, 3)
    assert abs(D(str(f["anchors"]["qty"])) - D("5.433")) <= D("0.001")
    assert D(str(f["chairs"]["qty"])) == 4 and abs(D(str(f["tie_wire"]["qty"])) - D("3.768")) <= D("0.001")
    assert D(str(f["cure"]["qty"])) == 4
    assert "tack_strips" in f and D(str(f["tack_strips"]["qty"])) == 0
    # The tab's V97: CY / 300 loads, live on this tab and blank on 04.
    assert D(str(f["haul_off"]["qty"])) == D("3.313") and f["haul_off"]["taxable"] is False
    assert D(str(f["haul_off"]["ext_cost"])) == D("828.25")
    assert D(str(f["accessories"]["ext_cost"])) > D("1868")             # 46,7xx lb at the catalog's $0.04


# ------------------------------------------------------------ the money --


def test_the_material_list_and_the_barrier(db, estimate):
    section = _build(db, estimate)
    m = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert D(str(m["concrete"]["cost"])) == D("154069.29")             # 993.9954 CY x $155
    assert D(str(m["sand"]["cost"])) == D("4884.62")                   # 348.9012 CY x $14
    assert abs(D(str(m["rebar"]["cost"])) - D("30367.75")) < D("25")    # 46,7xx lb x $0.65
    assert "vapor_barrier" in m or "poly" in m or any("barrier" in k or "poly" in k for k in m), sorted(m)


def test_the_total_and_every_cent_of_the_variance(db, estimate):
    section = _build(db, estimate)
    assert _cost(db, section.id) == sf.GOLDEN_COST
    pieces = (
        + D("1013.01")  # accessories at the catalog's $0.04, not the tab's $0.02, taxed
        + D("288.34")   # fuel and tax on MISCELLANEOUS, which the sheet exempts (495 x 0.5825)
        + D("24.90")    # 35 lb of catalog bar weight, taxed
        + D("6.18")     # the tie-steel labor riding that weight
        - D("68.42")    # concrete haul-off untaxed here, a service, its loads kept to three places
        + D("0.08")     # the lumber block: the 2x4 at four decimals, the 2x10, anchors, tie wire
        + D("0.02")     # the concrete and the barrier, a cent each
    )
    named = sf.SHEET["total_cost"].quantize(D("0.01")) + pieces
    # Tax is figured once on the base here and line by line on the tab: cents.
    assert abs(named - sf.GOLDEN_COST) <= D("0.03"), named - sf.GOLDEN_COST


# ----------------------------------------------------------------- API --


def test_the_kind_is_offered_and_a_pour_saves(client, db, estimate):
    assert "slabs" in client.get("/api/sections/meta/kinds").json()
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "slabs", "name": "Slabs"})
    assert r.status_code == 201 and r.json()["unit"] == "SF", r.text
    sid = r.json()["id"]
    mix = client.get("/api/mix-designs").json()[0]["id"]
    r = client.post("/api/mono-slabs", json={
        "section_id": sid, "description": "P1", "square_footage": "1000", "thickness_in": "5",
        "sand_thickness_in": "2", "perimeter_edge_lf": "130", "mix_design_id": mix,
        "post_tension": False, "wire_mesh": False, "slab_bar_size": 3, "slab_bar_spacing_in": "12",
    })
    assert r.status_code == 201, r.text
    assert D(r.json()["calc_support_rebar_lb"]) == 0, "no support steel on a rebar slab"
    rates = {x["key"] for x in client.get(f"/api/sections/{sid}/rates").json()["rows"]}
    assert {"labor_grading_sf", "labor_tie_steel_free_lb_per_sf", "saw_cutting_lf", "saw_joint_spacing_ft"} <= rates
    eq = client.get(f"/api/sections/{sid}/equipment").json()
    codes = {ln["code"] for ln in eq["lines"]}
    assert {"saw_cutting", "saw_joint_sealant", "concrete_pump"} <= codes
