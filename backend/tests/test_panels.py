"""
Tilt-wall panels (sql/077, 2026-09-08): the 12-PANELS tab Chad seeded, as a
panel type and its count — the seventh takeoff shape — with four opening
slots per type where the tab has one.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text

from app.models.panel_type import PanelType
from app.services import panels as pn
from app.services.costing import allocation_basis, refresh_pour_costs
from app.services.estimate_equipment import load_stored_equipment, refresh_and_store_equipment
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.material_costs import section_material_costs
from app.services.panels import section_panel_totals
from app.services.recalc import recalc_section
from tests import panels_fixture as pf

D = Decimal
TAX = D("1.0825")


def _build(db, estimate, *, sheet_mode: bool = False):
    section = pf.build(db, estimate, sheet_mode=sheet_mode)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    pf.type_the_supervision(db, section.id)
    # The foreman and the expense follow the typed days on the next refresh,
    # and the ladder follows them; recalc rewrites every stored takeoff once.
    recalc_section(db, section, pours=False)
    db.flush()
    return section


def _lines(payload) -> dict:
    return {ln["code"]: ln for ln in payload["lines"]}


def _row(db, section, label: str) -> PanelType:
    return db.scalars(
        select(PanelType).where(PanelType.section_id == section.id, PanelType.label == label)
    ).one()


def _section(db, section_id) -> dict:
    return db.execute(
        text("SELECT unit, calc_total_cost, calc_total_tax, calc_total_sale, calc_quantity, "
             "calc_cost_per_unit, calc_sale_per_unit, calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).mappings().one()


# ----------------------------------------------------------- the takeoff --


def test_the_tabs_quantities(db, estimate):
    t = section_panel_totals(db, _build(db, estimate).id)
    assert t["panel_count"] == pf.SHEET["panels"] and t["type_count"] == pf.SHEET["types"]
    assert D(str(t["total_sf"])) == pf.SHEET["total_sf"]
    assert D(str(t["total_perimeter_lf"])) == pf.SHEET["perimeter_lf"]
    assert D(str(t["total_bottom_lf"])) == pf.SHEET["bottom_lf"]
    # One 10 x 3 opening on every one of 36 panels: 30 SF and 26 LF apiece.
    assert D(str(t["total_opening_sf"])) == D("1080") and D(str(t["total_opening_lf"])) == D("936")
    assert abs(D(str(t["total_concrete_cy"])) - pf.SHEET["concrete_cy"]) <= D("0.001")
    assert allocation_basis("panels") == "SF"


def test_the_steel_is_the_tabs_with_the_bracket_closed(db, estimate):
    """
    `sheet_mode` restores the tab's bar constant, so the only gap left is the
    opening term: the tab adds `count x length` as bare pounds where the
    bracket it dropped makes it `(count x length + count x height) x 2 x w`.
    The difference on one panel is count x length x (2w - 1), wasted.
    """
    section = _build(db, estimate, sheet_mode=True)
    w5 = pn.sheet_bar_lb_per_ft(5)
    p1 = _row(db, section, "P1")
    bracket = D("2") * D("29") * (D("2") * w5 - D("1")) * D("1.05")
    assert abs(D(str(p1.calc_steel_each_lb)) - (pf.SHEET["u10_steel_each"] + bracket)) < D("0.01")
    assert abs(D(str(p1.calc_concrete_cy)) / D("3") - pf.SHEET["v10_cy_each"]) < D("0.001")

    t = section_panel_totals(db, section.id)
    lengths = sum(D(length) * qty for _, qty, length, _, _ in pf.TYPES)
    total_bracket = D("2") * lengths * (D("2") * w5 - D("1")) * D("1.05")
    assert abs(D(str(t["total_rebar_lb"])) - pf.SHEET["steel_lb"] - total_bracket) < D("0.05")


def test_the_bar_weights_are_the_catalogs(db, estimate):
    """ASTM #4 0.668 and #5 1.043 against the tab's 0.6689 and 1.0452: about 0.2% lighter."""
    app = section_panel_totals(db, _build(db, estimate).id)
    sheet = section_panel_totals(db, _build(db, estimate, sheet_mode=True).id)
    ratio = D(str(app["total_rebar_lb"])) / D(str(sheet["total_rebar_lb"]))
    assert D("0.997") < ratio < D("0.999")


def test_each_opening_adds_steel_and_lumber_and_takes_concrete(db, estimate):
    """
    Four slots, each a real opening: one more set of edge bars, its area off
    the concrete, its perimeter on the formed edge (Chad, 2026-09-08).
    """
    from app.models.estimate_section import EstimateSection

    priced = pf.price_the_catalog(db)
    section = EstimateSection(estimate_id=estimate.id, **pf.SECTION)
    db.add(section)
    db.flush()
    base = dict(section_id=section.id, qty=1, mix_design_id=priced["mix_id"], length_ft=D("30"),
                thickness_in=D("7.25"), top_el_ft=D("30"), bot_el_ft=D("0"), **pf.STEEL)
    one = PanelType(label="one", open1_len_ft=D("10"), open1_wide_ft=D("3"), sort_order=0, **base)
    four = PanelType(label="four", open1_len_ft=D("10"), open1_wide_ft=D("3"),
                     open2_len_ft=D("10"), open2_wide_ft=D("3"), open3_len_ft=D("4"), open3_wide_ft=D("4"),
                     open4_len_ft=D("6"), open4_wide_ft=D("8"), sort_order=10, **base)
    db.add_all([one, four])
    db.flush()
    for r in (one, four):
        pn.refresh_panel_type_calcs(db, r, section)
    db.flush()   # the drivers read in raw SQL, and the session does not autoflush

    # Steel: three more sets of (2 x 30 + 2 x 30) x 2 x 1.043 lb, with 5% waste.
    edge_set = (D("2") * D("30") + D("2") * D("30")) * D("2") * D("1.043")
    assert D(str(four.calc_steel_each_lb)) - D(str(one.calc_steel_each_lb)) == (
        D("3") * edge_set * D("1.05")
    ).quantize(D("0.001"))
    # Concrete: 30 + 16 + 48 more SF of hole, 7.25" thick, with 4% waste.
    assert D(str(one.calc_concrete_cy)) - D(str(four.calc_concrete_cy)) == (
        D("94") * D("7.25") / D("324") * D("1.04")
    ).quantize(D("0.0001"))
    # Formed perimeter: the openings' perimeters, on top of the panel's 120 LF.
    assert D(str(one.calc_opening_lf)) == D("26") and D(str(four.calc_opening_lf)) == D("96")
    assert D(str(one.calc_sf_each)) == D(str(four.calc_sf_each)) == D("900"), "SF is gross"

    refresh_and_store_forming(db, section.id)
    f = _lines(load_stored_forming(db, section.id))
    assert D(str(f["2x4"]["qty"])) == (D("240") + D("122")) * D("0.4")          # (edges + openings) x 40%
    assert D(str(f["2x8"]["qty"])) == (D("240") + D("122")) * D("0.4")          # both 7.25", both 2x8
    assert D(str(f["2x6"]["qty"])) == D("60") * D("2")                          # bottom LF x 2, no thin panels
    assert D(str(f["chamfer"]["qty"])) == (D("240") + D("122")) * D("2")


# --------------------------------------------------------------- labor --


def test_the_labor_and_supervision_are_the_tabs(db, estimate):
    section = _build(db, estimate)
    labor = load_stored_labor(db, section.id)
    lines = _lines(labor)
    assert D(str(lines["forming"]["ext_cost"])) == D("10508.40")                # 30,024 x 0.35
    assert D(str(lines["place_finish"]["ext_cost"])) == D("19515.60")
    assert D(str(lines["wreck"]["ext_cost"])) == D("7506.00")
    assert D(str(lines["rub_patch"]["ext_cost"])) == D("25520.40")
    assert D(str(lines["backfill"]["qty"])) == D("501.2222")                    # 1,041 x 6.5 x 2 / 27
    assert D(str(lines["backfill"]["ext_cost"])) == D("4009.78")
    assert D(str(lines["brick_ledge"]["qty"])) == 0 and D(str(lines["brick_ledge"]["rate"])) == D("1.5")
    t = section_panel_totals(db, section.id)
    assert D(str(lines["tie_steel"]["qty"])) == (D(str(t["total_rebar_lb"])) / D("2000")).quantize(D("0.0001"))
    assert "grading" not in lines and "curb" not in lines and "footings" not in lines
    # D88 typed 40; D89 = D88, D90 = D88; no PM row on the tab.
    assert D(str(lines["superintendent"]["qty"])) == 40 and D(str(lines["superintendent"]["ext_cost"])) == D("14000.00")
    assert D(str(lines["foreman"]["qty"])) == 40 and D(str(lines["foreman"]["ext_cost"])) == D("10000.00")
    assert D(str(lines["expense"]["qty"])) == 40 and D(str(lines["expense"]["ext_cost"])) == D("4000.00")
    assert D(str(lines["pm"]["qty"])) == 0
    assert D(str(labor["total_supervision_cost"])) == pf.SHEET["supervision"]
    assert labor["drivers"]["super_days_are_typed"] is True
    assert labor["drivers"]["panel_count"] == 36 and D(str(labor["drivers"]["bottom_lf"])) == D("1041")


# ----------------------------------------------------------- equipment --


def test_the_equipment_ladder_rides_the_typed_days(db, estimate):
    section = _build(db, estimate)
    eq = load_stored_equipment(db, section.id)
    lines = _lines(eq)
    assert D(str(eq["drivers"]["super_days"])) == 40 and D(str(eq["drivers"]["equip_days"])) == 60
    # 60 days over 29 bill days / 30 x 9: 18 units of each rate.
    assert D(str(lines["skytrack"]["ext_cost"])) == D("7650.00")
    assert D(str(lines["mini_excavator"]["ext_cost"])) == D("7650.00")           # the tab's 425
    assert D(str(lines["skid_steer"]["ext_cost"])) == D("5850.00")
    assert D(str(lines["compactor"]["ext_cost"])) == D("2250.00")                # the tab's 125
    assert D(str(lines["misc_equip"]["ext_cost"])) == D("630.00")
    assert lines["trencher"]["enabled"] is False
    assert abs(D(str(lines["concrete_pump"]["ext_cost"])) - D("13471.47")) < D("0.01")
    assert D(str(lines["panel_engineering"]["days_qty"])) == 12 and D(str(lines["panel_engineering"]["ext_cost"])) == D("1080.00")
    for code in ("waterproofing", "saw_cutting", "haul_off", "out_of_town"):
        assert D(str(lines[code]["ext_cost"])) == 0, code
    assert abs(D(str(eq["total_contract_cost"])) - pf.SHEET["contract"]) < D("0.01")


# ------------------------------------------------------------- forming --


def test_the_lumber_runs_off_the_formed_perimeter(db, estimate):
    section = _build(db, estimate)
    forming = load_stored_forming(db, section.id)
    f = _lines(forming)
    formed = pf.SHEET["perimeter_lf"] + D("936")                               # edges + openings
    assert D(str(f["2x4"]["qty"])) == formed * D("0.4")                          # 2,016
    assert D(str(f["2x6"]["qty"])) == pf.SHEET["lumber_2x6_lf"]                 # bottom x 2, no thin panels
    assert D(str(f["2x8"]["qty"])) == formed * D("0.4")
    assert D(str(f["2x10"]["qty"])) == pf.SHEET["bottom_lf"]                    # counted, not 347
    assert D(str(f["stakes"]["qty"])) == D("8.064")                              # 2,016 / 100 x 40%
    assert (D(str(f["16p"]["qty"])), D(str(f["8p"]["qty"])), D(str(f["6p"]["qty"]))) == (6, D("3.6"), D("3.6"))
    assert D(str(f["chamfer"]["qty"])) == formed * D("2")
    assert D(str(f["patch"]["qty"])) == D("120.096")                             # SF / 250
    assert D(str(f["chairs"]["qty"])) == 6 and D(str(f["chairs"]["unit_cost"])) == D("45")
    assert D(str(f["lift_inserts"]["qty"])) == 288 and D(str(f["brace_inserts"]["qty"])) == 108
    assert D(str(f["cure"]["qty"])) == 2 and D(str(f["bond_breaker"]["qty"])) == D("2.729")
    assert D(str(f["carton_forms"]["qty"])) == D("1145.1") and D(str(f["carton_forms"]["ext_cost"])) == D("1145.10")
    assert D(str(f["durrock_retainer"]["qty"])) == D("2290.2") and D(str(f["durrock_retainer"]["ext_cost"])) == D("4122.36")
    assert f["form_rental"]["enabled"] is False
    for code in ("ply", "anchors", "keyway", "wall_ties", "reveal", "bracing", "turnbuckles", "bolsters", "smooth_dowels"):
        assert D(str(f[code]["qty"])) == 0, code
    assert f["reveal"]["unit_cost"] == D("2.5") and f["bracing"]["material_name"] == "PIPE BRACING"
    assert forming["missing_prices"] == []


# ------------------------------------------------------------ the money --


def test_the_material_list(db, estimate):
    section = _build(db, estimate)
    m = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert abs(D(str(m["concrete"]["cost"])) - pf.SHEET["concrete_cy"] * D("155")) < D("0.05")
    assert m["rebar"]["unit_cost"] == D("0.6500") and "GRADE BEAM" in m["rebar"]["detail"]
    assert set(m) == {"concrete", "rebar"}


def test_the_total_and_every_cent_of_the_variance(db, estimate):
    section = _build(db, estimate)
    row = _section(db, section.id)
    t = section_panel_totals(db, section.id)
    f = _lines(load_stored_forming(db, section.id))
    assert row["unit"] == "SF" and D(str(row["calc_quantity"])) == pf.SHEET["total_sf"]
    assert D(str(row["calc_total_cost"])) == pf.GOLDEN_COST

    # 1. steel: the closed bracket less the catalog's lighter bar, with what rides it
    dlb = D(str(t["total_rebar_lb"])) - pf.SHEET["steel_lb"]
    steel = dlb * D("0.65") * TAX + dlb / D("2000") * D("450") + dlb * D("0.04") * TAX
    # 2. the openings are formed: 936 LF of blockout on the 2x4, the 2x8, the
    #    stakes and the chamfer, at the tab's own lumber prices
    lumber = (
        (D(str(f["2x4"]["qty"])) - pf.SHEET["lumber_2x4_lf"]) * pf.TAB_LUMBER["2 X 4  X 16'"]
        + (D(str(f["2x8"]["qty"])) - pf.SHEET["lumber_2x8_lf"]) * pf.TAB_LUMBER["2 X 8 X 16'"]
        + (D(str(f["stakes"]["qty"])) - pf.SHEET["stakes_bundles"]) * D("24")
        + (D(str(f["chamfer"]["qty"])) - pf.SHEET["chamfer_lf"]) * D("0.25")
    ) * TAX
    # 3. the 2x10 counts the panels
    x10 = (pf.SHEET["bottom_lf"] - pf.SHEET["sum_of_lengths"]) * pf.TAB_LUMBER["2 X 10 X 16'"] * TAX
    # 4. fuel and tax on MISCELLANEOUS, which the sheet exempts (630 x 0.5825)
    misc = D("630") * D("0.5825")
    # 5. the catalog's four-place lumber prices against the tab's eight
    places = sum(
        (D(str(f[code]["qty"])) * (pf.MATERIAL_PRICES[name] - pf.TAB_LUMBER[name])
         for code, name in (("2x4", "2 X 4  X 16'"), ("2x6", "2 X 6 X 16'"),
                            ("2x8", "2 X 8 X 16'"), ("2x10", "2 X 10 X 16'"))),
        D("0"),
    ) * TAX
    # 6. the bond breaker to three places
    drums = (D(str(f["bond_breaker"]["qty"])) - pf.SHEET["bond_breaker_drums"]) * D("635") * TAX

    named = pf.SHEET["total_cost"] + steel + lumber + x10 + misc + places + drums
    assert abs(named - pf.GOLDEN_COST) <= D("0.10"), named - pf.GOLDEN_COST
    # Sale at the section's 18%, per SF beside it.
    # Sale is rounded per row and summed: twelve rows, a cent or two either way.
    assert abs(D(str(row["calc_total_sale"])) - pf.GOLDEN_COST * D("1.18")) <= D("0.06")
    assert D(str(row["calc_cost_per_unit"])) == (pf.GOLDEN_COST / pf.SHEET["total_sf"]).quantize(D("0.0001"))
    assert not [x for x in row["calc_unpriced"] if "mobilization" not in x], row["calc_unpriced"]
    # And the tab's own per-panel figure lands where the app's does, near enough.
    assert abs(D(str(t["cost_per_panel"])) - pf.SHEET["total_cost"] / D("36")) < D("150")


# ----------------------------------------------------------------- API --


def test_the_grid_saves_a_panel_with_openings(client, db, estimate):
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "panels", "name": "Panels"})
    assert r.status_code == 201 and r.json()["unit"] == "SF", r.text
    sid = r.json()["id"]
    mix = client.get("/api/mix-designs").json()[0]["id"]
    rows = [{
        "label": "P1", "qty": 3, "mix_design_id": mix, "length_ft": "30", "thickness_in": "7.25",
        "top_el_ft": "26", "bot_el_ft": "-4",
        "open1_len_ft": "10", "open1_wide_ft": "3", "open2_len_ft": "4", "open2_wide_ft": "4",
        "horiz_spacing_in": "12", "horiz_size": 4, "horiz_mats": 2,
        "vert_spacing_in": "12", "vert_size": 5, "vert_mats": 2,
        "edge_bar_count": 2, "edge_bar_size": 5, "corner_bar_count": 2, "corner_bar_size": 5,
    }]
    r = client.put("/api/panel-types/bulk", json={"section_id": sid, "rows": rows})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    saved = body["rows"][0]
    assert D(saved["calc_height_ft"]) == 30 and D(saved["calc_sf"]) == 2700
    assert D(saved["calc_opening_sf"]) == 138 and D(saved["calc_opening_lf"]) == 126
    assert D(saved["calc_total_rebar_lb"]) > 0 and D(saved["calc_cost"]) > 0
    assert saved["calc_cost_per_panel"] is not None
    assert body["totals"]["panel_count"] == 3 and D(body["totals"]["total_bottom_lf"]) == 90

    # Nothing typed for supervision yet: the section says so rather than pricing the ladder at 0 days.
    sec = client.get(f"/api/sections/{sid}").json()
    assert any("superintendent days" in x for x in sec["calc_unpriced"]), sec["calc_unpriced"]

    rates = {x["key"] for x in client.get(f"/api/sections/{sid}/rates").json()["rows"]}
    assert {"labor_rub_patch_sf", "labor_backfill_cy", "panel_engineering_ea", "carton_forms_lf",
            "lift_inserts_per_panel", "backfill_width_ft"} <= rates
    assert "labor_curb_lf" not in rates and "labor_grading_sf" not in rates
    codes = {ln["code"] for ln in client.get(f"/api/sections/{sid}/equipment").json()["lines"]}
    assert {"skytrack", "compactor", "panel_engineering", "concrete_pump", "mobilization"} <= codes
    assert client.get(f"/api/sections/{sid}").json()["quote_kinds"] == ["rebar"]

    # A row with no height is not a panel.
    r = client.put("/api/panel-types/bulk", json={"section_id": sid, "rows": [
        {"label": "flat", "qty": 1, "length_ft": "30", "thickness_in": "7", "top_el_ft": "0", "bot_el_ft": "0"},
    ]})
    assert r.status_code == 400 and "elevation" in r.json()["detail"]
