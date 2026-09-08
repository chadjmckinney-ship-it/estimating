"""
Grade beams and continuous footings (sql/073, 2026-09-07): the Pearl Landing
Podium 02-Gd Beams and 02-Cont Footings tabs as sections on one engine.

Chad: "we can do cont footings when we do grade beams" — "we use LF for both
of those."
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
from tests import grade_beams_fixture as gb

D = Decimal


def _finish(db, section, *, footings: bool):
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    gb.type_the_supervision(db, section.id, footings=footings)
    if not footings:
        gb.switch_off_the_cartons(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _beams(db, estimate):
    return _finish(db, gb.build(db, estimate), footings=False)


def _footings(db, estimate):
    return _finish(db, gb.build_footings(db, estimate), footings=True)


def _cost(db, section_id) -> Decimal:
    return D(str(db.scalar(text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"), {"i": str(section_id)})))


def _row(db, section_id) -> dict:
    return db.execute(text("SELECT unit, calc_quantity, calc_total_cost, calc_total_sale, calc_cost_per_unit, "
                           "calc_unpriced FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}).mappings().one()


def _lines(payload) -> dict:
    return {ln["code"]: ln for ln in payload["lines"]}


def _quantities(db, section_id) -> dict:
    return db.execute(text("SELECT length_ft, calc_face_ff, calc_contact_ff, calc_concrete_cy, "
                           "calc_total_rebar_lb, calc_excavate_cy, calc_backfill_cy FROM beam_runs "
                           "WHERE section_id = :i"), {"i": str(section_id)}).mappings().one()


# ----------------------------------------------------------- the takeoff --


def test_the_beams_tabs_quantities(db, estimate):
    q = _quantities(db, _beams(db, estimate).id)
    s = gb.BEAMS_SHEET
    assert D(str(q["length_ft"])) == s["length_lf"]
    assert D(str(q["calc_face_ff"])) == s["face_ff"]
    assert D(str(q["calc_contact_ff"])) == s["contact_ff"]
    assert abs(D(str(q["calc_concrete_cy"])) - s["concrete_cy"]) <= D("0.001")
    # Catalog bar weights against the tab's own constants: a tenth of a percent.
    assert abs(D(str(q["calc_total_rebar_lb"])) - s["steel_lb"]) / s["steel_lb"] < D("0.001")
    assert D(str(q["calc_excavate_cy"])) == s["excavate_cy"]
    assert D(str(q["calc_backfill_cy"])) == s["backfill_cy"]


def test_the_footings_tabs_quantities(db, estimate):
    q = _quantities(db, _footings(db, estimate).id)
    s = gb.FOOTINGS_SHEET
    assert D(str(q["length_ft"])) == s["length_lf"]
    assert D(str(q["calc_face_ff"])) == s["face_ff"]
    assert abs(D(str(q["calc_concrete_cy"])) - s["concrete_cy"]) <= D("0.001")
    assert abs(D(str(q["calc_total_rebar_lb"])) - s["steel_lb"]) / s["steel_lb"] < D("0.001")
    assert D(str(q["calc_excavate_cy"])) == s["excavate_cy"]
    assert D(str(q["calc_backfill_cy"])) == s["backfill_cy"]


def test_the_sheet_bar_weights_reproduce_the_tab(db, estimate):
    """sheet_mode swaps the tab's constants in; the steel then lands on W36 exactly."""
    section = gb.build(db, estimate, sheet_mode=True)
    q = _quantities(db, section.id)
    assert abs(D(str(q["calc_total_rebar_lb"])) - gb.BEAMS_SHEET["steel_lb"]) <= D("0.01")


def test_no_stirrup_spacing_means_no_stirrups_not_no_steel(db, estimate):
    from app.models.beam_run import BeamRun
    from app.services.beams import refresh_beam_run_calcs

    section = gb.build(db, estimate)
    run = db.query(BeamRun).filter(BeamRun.section_id == section.id).one()
    with_stirrups = D(str(run.calc_total_rebar_lb))
    run.stirrup_spacing_in = None
    refresh_beam_run_calcs(db, run, section)
    bars_only = D(str(run.calc_total_rebar_lb))
    # Six #6 bars over 1,248 ft at 1.502 lb/ft, wasted 10%: the tab would say 0.
    assert abs(bars_only - D("6") * D("1248") * D("1.502") * D("1.10")) < D("1")
    assert D("0") < bars_only < with_stirrups


def test_both_kinds_sell_per_lf(db, estimate):
    for section, lf in ((_beams(db, estimate), gb.BEAMS_LF), (_footings(db, estimate), gb.FOOTINGS_LF)):
        row = _row(db, section.id)
        assert row["unit"] == "LF" and D(str(row["calc_quantity"])) == lf
        assert D(str(row["calc_cost_per_unit"])) == (D(str(row["calc_total_cost"])) / lf).quantize(D("0.0001"))


# --------------------------------------------------------------- labor --


def test_the_labor_is_the_tabs(db, estimate):
    section = _beams(db, estimate)
    labor = _lines(load_stored_labor(db, section.id))
    assert D(str(labor["forming"]["ext_cost"])) == D("12480.00")       # 3,120 FF x $4
    assert D(str(labor["place_finish"]["ext_cost"])) == D("12480.00")
    assert D(str(labor["wreck"]["ext_cost"])) == D("3120.00")
    assert D(str(labor["rub_patch"]["ext_cost"])) == D("780.00")
    assert D(str(labor["excavate"]["ext_cost"])) == D("2116.00")       # 529 CY x $4
    assert D(str(labor["backfill"]["ext_cost"])) == D("2312.00")       # 289 CY x $8
    assert abs(D(str(labor["tie_steel"]["ext_cost"])) - D("3829.46")) < D("5")
    assert D(str(labor["pilasters"]["qty"])) == 0
    assert "footings" not in labor and "french_drains" not in labor, "walls lines, not beam lines"
    assert D(str(labor["superintendent"]["ext_cost"])) == D("2125.00")
    assert D(str(labor["pm"]["ext_cost"])) == D("1000.00")


def test_the_equipment_ladder_is_the_tabs(db, estimate):
    """Five superintendent days rent seven; 4-7 days bill three units (E78:E83, N78:N83)."""
    section = _beams(db, estimate)
    eq = _lines(load_stored_equipment(db, section.id))
    assert D(str(eq["skytrack"]["ext_cost"])) == D("1275.00")         # 425 x 3, on the ladder here
    assert D(str(eq["mini_excavator"]["ext_cost"])) == D("1425.00")   # 475 x 3
    assert D(str(eq["skid_steer"]["ext_cost"])) == D("975.00")        # 325 x 3
    assert D(str(eq["light_tower"]["ext_cost"])) == D("300.00")
    assert D(str(eq["vault"]["ext_cost"])) == D("150.00")             # 50 x 3, on the ladder here
    assert D(str(eq["misc_equip"]["ext_cost"])) == D("105.00")
    assert D(str(eq["concrete_pump"]["ext_cost"])) == D("4807.11")     # 240.3556 CY x $20
    assert D(str(eq["haul_off"]["ext_cost"])) == D("1442.13")          # 240.3556 CY x $6, automatic
    assert "saw_cutting" in eq and D(str(eq["saw_cutting"]["ext_cost"])) == 0


# ------------------------------------------------------------- forming --


def test_the_lumber_block_is_the_tabs(db, estimate):
    section = _beams(db, estimate)
    f = _lines(load_stored_forming(db, section.id))
    assert D(str(f["stakes"]["qty"])) == 25 and D(str(f["stakes"]["ext_cost"])) == D("600.00")
    assert (D(str(f["16p"]["qty"])), D(str(f["8p"]["qty"])), D(str(f["6p"]["qty"]))) == (2, 4, 4)
    assert D(str(f["chamfer"]["qty"])) == 2496 and D(str(f["chamfer"]["ext_cost"])) == D("624.00")
    assert D(str(f["wall_ties"]["qty"])) == 18 and D(str(f["wall_ties"]["ext_cost"])) == D("810.00")
    assert D(str(f["camlocks"]["qty"])) == 2080 and D(str(f["camlocks"]["ext_cost"])) == D("1787.55")  # 0.8594 x 2,080: the catalog keeps four decimals
    assert abs(D(str(f["haul_off"]["qty"])) - D("0.801")) <= D("0.001")
    assert D(str(f["accessories"]["ext_cost"])) > D("680")            # 17,0xx lb at the catalog's $0.04
    # % of forming is 0 on this job, so the lumber that rides it is 0.
    for code in ("2x4", "2x6", "2x10", "ply", "turnbuckles"):
        assert D(str(f[code]["qty"])) == 0, code
    # Lines the tab carries and zeroes by formula: here, and off.
    for code in ("keyway", "water_stop", "dowels", "form_rental"):
        assert f[code]["enabled"] is False and D(str(f[code]["ext_cost"])) == 0, code
    assert D(str(f["keyway"]["qty"])) == 1248 and D(str(f["dowels"]["qty"])) == 832  # 1,248 x 12 / 18
    # Typed n on the Podium beams.
    assert f["carton_forms"]["enabled"] is False and f["durrock_retainer"]["enabled"] is False
    assert "form_rental" not in load_stored_forming(db, section.id)["missing_prices"], "off is not unpriced"


def test_a_continuous_footing_starts_with_the_podium_tabs_switches(db, estimate):
    section = _footings(db, estimate)
    f = _lines(load_stored_forming(db, section.id))
    assert f["wall_ties"]["enabled"] is False and f["camlocks"]["enabled"] is False
    assert D(str(f["carton_forms"]["ext_cost"])) == gb.FOOTINGS_SHEET["carton_forms"]       # 184 x 1.1 x 3.75
    assert D(str(f["durrock_retainer"]["ext_cost"])) == gb.FOOTINGS_SHEET["durrock_retainer"]
    assert D(str(f["stakes"]["qty"])) == 4 and D(str(f["chamfer"]["qty"])) == 368


def test_switching_a_default_off_line_on_survives_a_refresh(db, estimate):
    from app.services.forming import set_forming_line_enabled

    section = _beams(db, estimate)
    set_forming_line_enabled(db, section.id, "keyway", True)
    refresh_and_store_forming(db, section.id)
    f = _lines(load_stored_forming(db, section.id))
    assert f["keyway"]["enabled"] is True and D(str(f["keyway"]["ext_cost"])) > 0
    assert f["water_stop"]["enabled"] is False


# ------------------------------------------------------------ the money --


def test_the_beams_total_and_every_cent_of_the_variance(db, estimate):
    section = _beams(db, estimate)
    assert _cost(db, section.id) == gb.BEAMS_GOLDEN_COST
    pieces = (
        + D("3371.00")  # tax on the concrete the tab's "200" cell left untaxed (40,860.45 x 0.0825), a cent of rounding in it
        + D("910.27")   # the steel: 2.6 lb lighter by catalog weight (-1.69 bar, -0.59 tie labor), then taxed (+912.55)
        + D("368.37")   # accessories at the catalog's $0.04, not the tab's $0.02, taxed
        - D("16.57")    # concrete haul-off untaxed here, a service, its loads kept to three places
        + D("61.16")    # fuel and tax on MISCELLANEOUS, which the sheet exempts
        + D("0.05")     # camlocks at the catalog's four decimals, 0.8594 not 0.859375
    )
    named = gb.BEAMS_SHEET["total_cost"].quantize(D("0.01")) + pieces
    # Tax is figured once on the base here and line by line on the tab: cents.
    assert abs(named - gb.BEAMS_GOLDEN_COST) <= D("0.03"), named - gb.BEAMS_GOLDEN_COST


def test_the_footings_total_and_every_cent_of_the_variance(db, estimate):
    section = _footings(db, estimate)
    assert _cost(db, section.id) == gb.FOOTINGS_GOLDEN_COST
    pieces = (
        + D("496.99")   # tax on the concrete (6,024.29 x 0.0825), a cent of rounding out of it
        + D("134.21")   # the steel: lighter by catalog weight (-0.25 bar, -0.08 tie labor), then taxed (+134.54)
        + D("154.46")   # carton forms and the retainer taxed here as the materials they are; the tab's O58/O59 carry no tax
        + D("54.31")    # accessories at the catalog's $0.04, taxed
        - D("2.47")     # haul-off untaxed here, its loads kept to three places
        + D("4.08")     # fuel and tax on MISCELLANEOUS (7 x 0.5825)
    )
    named = gb.FOOTINGS_SHEET["total_cost"].quantize(D("0.01")) + pieces
    assert abs(named - gb.FOOTINGS_GOLDEN_COST) <= D("0.03"), named - gb.FOOTINGS_GOLDEN_COST


def test_the_material_list_is_the_two_lines(db, estimate):
    section = _beams(db, estimate)
    m = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert set(m) == {"concrete", "rebar"}
    assert D(str(m["concrete"]["cost"])) == D("40860.45")   # 240.3556 CY x $170
    assert m["rebar"]["unit_cost"] == D("0.6500")


# ----------------------------------------------------------------- API --


def test_the_kinds_are_offered_and_a_grid_row_saves(client, db, estimate):
    kinds = client.get("/api/sections/meta/kinds").json()
    assert "grade_beams" in kinds and "cont_footings" in kinds
    for kind in ("grade_beams", "cont_footings"):
        r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": kind, "name": kind})
        assert r.status_code == 201, r.text
        assert r.json()["unit"] == "LF"
        sid = r.json()["id"]
        mix = client.get("/api/mix-designs").json()[0]["id"]
        r = client.put("/api/beam-runs/bulk", json={"section_id": sid, "rows": [{
            "label": "GB1", "mix_design_id": mix, "length_ft": "100", "width_in": "12", "height_in": "24",
            "top_bars_count": 2, "top_bars_size": 5, "bottom_bars_count": 2, "bottom_bars_size": 5,
            "stirrup_size": 3, "stirrup_spacing_in": "18",
        }]})
        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert D(row["calc_face_ff"]) == D("200") and D(row["calc_contact_ff"]) == D("400")
        t = r.json()["totals"]
        assert t["run_count"] == 1 and D(t["total_length_ft"]) == D("100")
        rates = {x["key"] for x in client.get(f"/api/sections/{sid}/rates").json()["rows"]}
        assert {"labor_pilasters_ff", "labor_forming_sf", "carton_forms_lf", "concrete_pump_cy"} <= rates
        assert "labor_footings_sf" not in rates
        from app.services.quotes import kinds_for

        assert "rebar" in kinds_for(kind), "a fabricator quote prices beam steel too"
        r = client.put("/api/beam-runs/bulk", json={"section_id": sid, "rows": [{"label": "x", "width_in": "12"}]})
        assert r.status_code == 400 and "length" in r.text


def test_a_beams_section_is_guarded_on_delete(client, db, estimate):
    section = gb.build(db, estimate)
    r = client.delete(f"/api/sections/{section.id}")
    assert r.status_code == 409 and "beam runs" in r.json()["detail"], r.text
    assert client.delete(f"/api/sections/{section.id}?force=true").status_code == 204
