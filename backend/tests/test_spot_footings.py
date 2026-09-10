"""
Spot footings (sql/072, 2026-09-07): the Pearl Landing Podium 06-Footings tab
as a section of its own on the walls engine.

Chad: "most spread footings have a weld plate.. so I think we need a section
for spread footings and one for continuous footings.. we can do cont footings
when we do grade beams.. for spot footings, the wall calc works if we do l w
and h with a count.. t&b mats"

The sheet reads $187,680.06 and every difference between that and the app's
number is named in spot_footings_fixture.py.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text

from app.models.wall_run import WallRun
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.material_costs import section_material_costs
from app.services.recalc import recalc_section
from tests import spot_footings_fixture as sf

D = Decimal


def _build(db, estimate):
    section = sf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    sf.type_the_supervision(db, section.id)
    sf.type_the_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _cost(db, section_id) -> Decimal:
    return D(str(db.scalar(text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"), {"i": str(section_id)})))


def _labor(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, section_id)["lines"]}


def _row(db, section_id) -> dict:
    return db.execute(text("SELECT unit, calc_quantity, calc_total_cost, calc_cost_per_unit, calc_unpriced "
                           "FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}).mappings().one()


# ----------------------------------------------------------- the takeoff --


def test_the_length_is_the_count_times_each(db, estimate):
    section = _build(db, estimate)
    runs = db.scalars(select(WallRun).where(WallRun.section_id == section.id).order_by(WallRun.sort_order)).all()
    assert [(r.footing_count, D(str(r.length_ft))) for r in runs] == [
        (6, D("60")), (17, D("144.5")), (47, D("305.5")), (16, D("48")),
    ]
    assert all(D(str(r.calc_form_ff)) == 0 and D(str(r.calc_wall_concrete_cy)) == 0 for r in runs), "no wall"


def test_the_sheets_quantities(db, estimate):
    section = _build(db, estimate)
    t = db.execute(text("SELECT sum(footing_count) AS n, sum(length_ft) AS lf, sum(calc_footing_sf) AS sf, "
                        "sum(calc_footing_concrete_cy) AS cy, sum(calc_total_rebar_lb) AS lb, "
                        "sum(calc_excavate_cy) AS dig FROM wall_runs WHERE section_id = :i"),
                   {"i": str(section.id)}).mappings().one()
    assert t["n"] == sf.SHEET["footings"]
    assert D(str(t["lf"])) == sf.SHEET["length_lf"]
    assert D(str(t["sf"])) == sf.SHEET["footer_sf"]
    assert abs(D(str(t["cy"])) - sf.SHEET["concrete_cy"]) <= D("0.001")
    # Catalog bar weight against the sheet's 10.680159 factor: a tenth of a percent.
    assert abs(D(str(t["lb"])) - sf.SHEET["steel_lb"]) / sf.SHEET["steel_lb"] < D("0.001")
    # 3888, not the sheet's 3088 (Chad, 2026-09-05): the footings' own volume,
    # rounded row by row the way the sheet's DD column rounds it.
    assert D(str(t["dig"])) == D("302")


def test_it_is_sold_per_footing(db, estimate):
    section = _build(db, estimate)
    row = _row(db, section.id)
    assert row["unit"] == "EA" and int(row["calc_quantity"]) == 86
    assert D(str(row["calc_cost_per_unit"])) == (D(str(row["calc_total_cost"])) / 86).quantize(D("0.0001"))


# --------------------------------------------------------------- labor --


def test_the_labor_is_the_footing_lines_only(db, estimate):
    section = _build(db, estimate)
    labor = _labor(db, section.id)
    assert D(str(labor["footings"]["ext_cost"])) == sf.SHEET["footings_labor"]
    assert abs(D(str(labor["tie_steel"]["ext_cost"])) - sf.SHEET["tie_steel_labor"]) < D("10")
    assert D(str(labor["excavate"]["qty"])) == D("302")
    assert D(str(labor["excavate"]["ext_cost"])) == D("3624.00")
    assert "french_drains" not in labor, "a wall line; there is no wall"
    # The footing's own forming, place & finish, wreck and rub & patch per face foot (sql/089):
    # there, at the footing's length x thickness x count, and off until the job prices them.
    face = D(str(db.execute(text(
        "SELECT sum(length_ft * ftg_thick_in / 12.0) FROM wall_runs WHERE section_id = :s"),
        {"s": str(section.id)}).scalar())).quantize(D("0.0001"))
    assert face > 0
    for code, rate in (("forming", "3.5"), ("place_finish", "3.5"), ("wreck", "1"), ("rub_patch", "0.25")):
        assert labor[code]["enabled"] is False and D(str(labor[code]["ext_cost"])) == 0, code
        assert D(str(labor[code]["qty"])) == face and D(str(labor[code]["rate"])) == D(rate), code
    assert {"superintendent", "foreman", "expense", "pm"} <= set(labor)
    assert D(str(labor["pm"]["ext_cost"])) == D("2000")


def test_the_equipment_ladder_is_the_sheets(db, estimate):
    """Ten superintendent days rent fourteen; 8-20 days bill days/7 x 3 (D84, N84)."""
    from app.services.estimate_equipment import load_stored_equipment

    section = _build(db, estimate)
    eq = {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}
    assert D(str(eq["mini_excavator"]["ext_cost"])) == D("2850.00")   # 475 x 6 billable
    assert D(str(eq["skytrack"]["ext_cost"])) == D("2550.00")         # typed 14 days, 425 x 6
    assert D(str(eq["vault"]["ext_cost"])) == D("300.00")             # typed 14 days, 50 x 6
    assert D(str(eq["misc_equip"]["ext_cost"])) == D("210.00")
    assert D(str(eq["concrete_pump"]["ext_cost"])) == D("3201.98")     # 320.1985 CY x $10
    assert D(str(eq["skytrack"]["days_qty"])) == 14


# --------------------------------------------------------- weld plates --


def test_weld_plates_are_counted_and_reported_unpriced_until_priced(db, estimate):
    section = _build(db, estimate)
    lines = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert D(str(lines["weld_plates"]["qty"])) == 86 and lines["weld_plates"]["unit"] == "EA"
    assert lines["weld_plates"]["unit_cost"] is None
    assert any("WELD PLATE" in x for x in _row(db, section.id)["calc_unpriced"])
    before = _cost(db, section.id)

    db.execute(text("UPDATE materials SET unit_cost = 45 WHERE upper(name) = 'WELD PLATE'"))
    db.flush()
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    recalc_section(db, section)
    db.flush()
    lines = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert D(str(lines["weld_plates"]["cost"])) == D("3870.00")  # 86 x $45
    assert not any("WELD PLATE" in x for x in _row(db, section.id)["calc_unpriced"])
    assert abs((_cost(db, section.id) - before) - D("3870.00") * D("1.0825")) <= D("0.02")


# ------------------------------------------------------------ the money --


def test_the_total_and_every_cent_of_the_variance(db, estimate):
    """
    The sheet's $187,680.06 and every cent between it and the app, each
    named in the fixture's docstring. If this moves, one of the tests above
    should have moved first.
    """
    section = _build(db, estimate)
    assert _cost(db, section.id) == sf.GOLDEN_COST
    pieces = (
        - D("936.00")   # excavation by 3888, not 3088 (380 CY -> 302 CY at $12)
        + D("1.98")     # the pump on 320.1985 CY, not the ROUNDed 320
        + D("122.33")   # fuel and tax on MISCELLANEOUS, which the sheet exempts
        + D("1.74")     # 2.47 lb of catalog bar weight, with its tax
        + D("0.53")     # the tie-steel labor riding that weight
        + D("0.03")     # the lumber block: 2x10 price, haul-off places, accessories
    )
    named = sf.SHEET["total_cost"].quantize(D("0.01")) + pieces
    assert abs(named - sf.GOLDEN_COST) <= D("0.01"), named - sf.GOLDEN_COST


# ----------------------------------------------------------------- API --


def test_the_kind_is_offered_and_a_grid_row_saves_as_a_footing(client, db, estimate):
    assert "spot_footings" in client.get("/api/sections/meta/kinds").json()
    r = client.post(f"/api/estimates/{estimate.id}/sections",
                    json={"kind": "spot_footings", "name": "Footings", "unit": "EA"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    mix = client.get("/api/mix-designs").json()[0]["id"]
    r = client.put("/api/wall-runs/bulk", json={"section_id": sid, "rows": [{
        "label": "F1", "footing_count": 4, "footing_each_ft": "5", "ftg_width_in": "60", "ftg_thick_in": "18",
        "footing_mix_design_id": mix, "ftg_bot_size": 5, "ftg_bot_spacing_in": "12",
        "ftg_top_size": 5, "ftg_top_spacing_in": "12", "weld_plate": True, "backfill": False,
    }]})
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert D(row["length_ft"]) == D("20") and D(row["calc_footing_sf"]) == D("100")
    t = r.json()["totals"]
    assert (t["footing_count"], t["weld_plate_count"], t["run_count"]) == (4, 4, 1)
    rates = {x["key"] for x in client.get(f"/api/sections/{sid}/rates").json()["rows"]}
    assert {"labor_footings_sf", "labor_tie_steel_ton", "labor_excavate_cy"} <= rates
    assert {"labor_forming_sf", "labor_place_finish_sf", "labor_wreck_sf", "labor_rub_patch_sf"} <= rates, \
        "the footing's face-foot lines read their rates (sql/089)"
    assert "labor_french_drain_lf" not in rates, "the wall's drain is not read on a footing"
