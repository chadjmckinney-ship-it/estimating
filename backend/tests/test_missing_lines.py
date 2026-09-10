"""
The lines the Lakeside tie-out found missing (sql/089).

Chad, 2026-09-10: "add the missing line sets, light tower, compactor, place
and finish". Every line off by default, so no priced job moves until
somebody switches one on: a light tower on the slab sets, a compactor on
the beam and wall/footing sets, and forming / place & finish / wreck / rub
& patch per face foot on a spot footing. Pinned: each is there, off, at $0,
with its quantity ready (the rental ladder's days; the footing's length x
thickness x count, the newer footings tab's FACE FT), priced off the
catalog or the kind's rate, and switching one on prices it the way the set
prices its neighbours.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services.estimate_equipment import get_or_refresh_equipment, update_equipment_line
from app.services.labor import get_or_refresh_labor, update_labor_line
from tests import grade_beams_fixture as gbf
from tests import mono_slab_fixture as mf
from tests import spot_footings_fixture as sff

D = Decimal


def _equipment(db, section_id):
    return {ln["code"]: ln for ln in get_or_refresh_equipment(db, section_id)["lines"]}


def _labor(db, section_id):
    return {ln["code"]: ln for ln in get_or_refresh_labor(db, section_id)["lines"]}


def test_a_slab_carries_a_light_tower_off_at_the_ladders_days(db, estimate):
    slab = mf.build(db, estimate)
    eq = _equipment(db, slab.id)
    tower = eq["light_tower"]
    assert tower["enabled"] is False and D(str(tower["ext_cost"])) == 0
    assert D(str(tower["days_qty"])) == D(str(eq["trencher"]["days_qty"])) > 0    # the ladder, like the trencher
    assert tower["equipment_id"] is not None and tower["price_source"] in ("sheet", "catalog")   # the catalog's row on the job's sheet, not a guess
    assert "Off by default" in tower["notes"]
    assert list(eq).index("skid_steer") < list(eq).index("light_tower") < list(eq).index("vault")
    # The LBJ golden is untouched: the slab's rental total is what it was.
    assert D(str(get_or_refresh_equipment(db, slab.id)["total_equipment_cost"])) == mf.GOLDEN_COST["equipment_rental"]
    # Switched on, it prices its days at its rate the way the neighbours do, and a
    # refresh keeps the switch.
    on = update_equipment_line(db, slab.id, "light_tower", enabled=True)
    line = next(ln for ln in on["lines"] if ln["code"] == "light_tower")
    assert line["enabled"] and D(str(line["ext_cost"])) == (D(str(line["billable_units"])) * D(str(line["rate"]))).quantize(D("0.01")) > 0
    from app.services.estimate_equipment import refresh_and_store_equipment

    again = {ln["code"]: ln for ln in refresh_and_store_equipment(db, slab.id)["lines"]}
    assert again["light_tower"]["enabled"] and D(str(again["light_tower"]["ext_cost"])) == D(str(line["ext_cost"]))


def test_beams_and_footings_carry_a_compactor_off(db, estimate):
    beams = gbf.build(db, estimate)
    footings = sff.build(db, estimate)
    comp_id = db.execute(text("SELECT id FROM equipment WHERE upper(name) = 'COMPACTOR'")).scalar()
    assert comp_id
    for section in (beams, footings):
        eq = _equipment(db, section.id)
        comp = eq["compactor"]
        assert comp["enabled"] is False and D(str(comp["ext_cost"])) == 0
        assert comp["equipment_id"] == comp_id and comp["price_source"] in ("sheet", "catalog") and D(str(comp["rate"])) == D("200")
        assert D(str(comp["days_qty"])) == D(str(eq["skid_steer"]["days_qty"]))
        assert list(eq).index("skid_steer") < list(eq).index("compactor") < list(eq).index("light_tower")


def test_a_spot_footing_carries_its_face_foot_labor_off(db, estimate):
    section = sff.build(db, estimate)
    labor = _labor(db, section.id)
    face = D(str(db.execute(text(
        "SELECT sum(length_ft * ftg_thick_in / 12.0) FROM wall_runs WHERE section_id = :s"),
        {"s": str(section.id)}).scalar())).quantize(D("0.0001"))
    assert face > 0
    for code, rate in (("forming", "3.5"), ("place_finish", "3.5"), ("wreck", "1"), ("rub_patch", "0.25")):
        ln = labor[code]
        assert ln["enabled"] is False and D(str(ln["ext_cost"])) == 0
        assert D(str(ln["qty"])) == face and D(str(ln["rate"])) == D(rate) and ln["unit"] == "/FF"
        assert "Off by default" in ln["notes"]
    assert "french_drains" not in labor and labor["footings"]["enabled"]
    # The sheet's golden is untouched: the four are off, so the footing's labor is what it was.
    assert D(str(labor["footings"]["ext_cost"])) == sff.SHEET["footings_labor"]
    # On, place & finish prices the face feet at the 06-Footings tab's rate.
    on = update_labor_line(db, section.id, "place_finish", enabled=True, mark_manual=None)
    ln = next(x for x in on["lines"] if x["code"] == "place_finish")
    assert ln["enabled"] and D(str(ln["ext_cost"])) == (face * D("3.5")).quantize(D("0.01"))
    # The rates came from the estimate's sheet, seeded from the assembly (sql/089).
    rates = {r[0]: D(str(r[1])) for r in db.execute(text(
        "SELECT ref_key, value FROM estimate_prices WHERE estimate_id = :e AND kind = 'assembly_rate' AND scope = 'spot_footings'"),
        {"e": str(estimate.id)}).all()}
    assert (rates["labor_forming_sf"], rates["labor_place_finish_sf"], rates["labor_wreck_sf"], rates["labor_rub_patch_sf"]) \
        == (D("3.5"), D("3.5"), D("1"), D("0.25"))
