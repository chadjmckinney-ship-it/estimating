"""
Miscellaneous (sql/078, 2026-09-08): the 13-Miscellaneous tab as a priced
library of site items — four families, a typed sale, the margin the answer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.misc_item import MiscItem
from app.services.costing import allocation_basis, refresh_pour_costs
from app.services.material_costs import section_material_costs
from app.services.misc import section_misc_totals
from tests import misc_fixture as mf

D = Decimal
TAX = D("1.0825")


def _build(db, estimate, **kw):
    section = mf.build(db, estimate, **kw)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def _rows(db, section) -> dict[str, MiscItem]:
    return {
        r.code: r
        for r in db.scalars(select(MiscItem).where(MiscItem.section_id == section.id)).all()
    }


def _section(db, section_id) -> dict:
    return db.execute(
        text("SELECT unit, calc_total_cost, calc_total_tax, calc_total_sale, calc_quantity, "
             "calc_cost_per_unit, calc_sale_per_unit, calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).mappings().one()


# ------------------------------------------------------------- the library --


def test_a_new_section_carries_the_library_at_no_quantity(client, db, estimate):
    """Chad: "the 4 sections with the ones shown as defaults, minus the quantities"."""
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "miscellaneous", "name": "Misc"})
    assert r.status_code == 201 and r.json()["unit"] == "LS", r.text
    sid = r.json()["id"]
    rows = client.get(f"/api/misc-items?section_id={sid}").json()
    assert len(rows) == 22
    assert {r["shape"] for r in rows} == {"round", "block", "slab", "box"}
    assert sum(1 for r in rows if r["shape"] == "round") == 4
    assert sum(1 for r in rows if r["shape"] == "block") == 6
    assert sum(1 for r in rows if r["shape"] == "slab") == 8
    assert sum(1 for r in rows if r["shape"] == "box") == 4
    assert all(D(r["qty"]) == 0 for r in rows)
    light = next(r for r in rows if r["code"] == "1301")
    assert light["description"] == "Light Pole Bases" and D(light["unit_sale"]) == 1150
    assert D(light["dim_a"]) == 24 and D(light["dim_b"]) == 8 and D(light["steel_lb_per_in_ft"]) == D("0.95")
    assert not next(r for r in rows if r["code"] == "1303")["pours_concrete"], "a bike rack is an install"
    sec = client.get(f"/api/sections/{sid}").json()
    assert D(sec["calc_total_cost"]) == 0 and D(sec["calc_total_sale"]) == 0
    assert sec["calc_unpriced"] == [], "nothing is bought at no quantity"
    assert sec["quote_kinds"] == ["rebar"]
    assert allocation_basis("miscellaneous") == "EA"


# ------------------------------------------------------------ the families --


@pytest.mark.parametrize("code", sorted(mf.QUANTITIES))
def test_each_item_is_the_tabs_row_with_decimal_yards_and_tax(db, estimate, code):
    """
    Every row prices the way the tab structures it — the same six pieces —
    with the yards kept in decimals and every purchase taxed.
    """
    section = _build(db, estimate)
    r = _rows(db, section)[code]
    tab = mf.tab_row(code, mf.QUANTITIES[code], exact=True)
    assert abs(D(str(r.calc_concrete_cy)) - tab["cy"]) <= D("0.0001"), code
    assert abs(D(str(r.calc_steel_lb)) - tab["lb"]) <= D("0.001"), code
    assert D(str(r.calc_sale)) == tab["sale"], code
    assert D(str(r.calc_labor_cost)) == tab["labor"].quantize(D("0.01")), code
    assert D(str(r.calc_super_cost)) == tab["sup"].quantize(D("0.01")), code
    assert abs(D(str(r.calc_equip_cost)) - tab["equip"]) <= D("0.01"), code
    # The purchases are stored pre-tax; the tab's exact structure carries the tax.
    assert abs(D(str(r.calc_concrete_cost)) * TAX - tab["concrete"]) <= D("0.02"), code
    assert abs(D(str(r.calc_steel_cost)) * TAX - tab["steel"]) <= D("0.02"), code
    assert abs(D(str(r.calc_forms_cost)) * TAX - tab["forms"]) <= D("0.02"), code
    assert abs(D(str(r.calc_cost)) - tab["cost"]) <= D("0.03"), (code, r.calc_cost, tab["cost"])
    if tab["sale"] > 0:
        assert D(str(r.calc_margin)) == ((tab["sale"] - D(str(r.calc_cost))) / tab["sale"]).quantize(D("0.0001"))


def test_the_round_base_is_pi_r_squared_depth_over_27(db, estimate):
    section = _build(db, estimate)
    light = _rows(db, section)["1301"]
    # 24" x 8': pi x 1^2 x 8 / 27 = 0.9308 CY a base, no waste, x 10.
    assert D(str(light.calc_concrete_cy)) == D("9.3084")
    assert D(str(light.calc_steel_lb)) == D("1824.000")           # 24 x 8 x 0.95 x 10
    assert D(str(light.calc_forms_cost)) == D("1525.00")          # 11,500 x 10% + 10 x 37.50
    assert D(str(light.calc_equip_cost)) == D("1390.00")          # 139 a base
    assert D(str(light.calc_super_cost)) == D("700.00")           # 20% of 3,500


def test_the_pit_gets_its_floor_and_its_face_forms(db, estimate):
    section = _build(db, estimate)
    pit = _rows(db, section)["1306"]
    # 48 LF x 16" x 72": walls 14.222 x 1.15 = 16.356 CY, a floor (48/4)^2 / 27 = 5.333.
    assert D(str(pit.calc_concrete_cy)) == D("21.6889")
    assert abs(D(str(pit.calc_steel_lb)) - D("21.68889") * D("145")) < D("0.01")
    assert D(str(pit.calc_face_sf)) == D("288.000")                # 48 x 72 / 12
    assert D(str(pit.calc_forms_cost)) == D("4014.00")            # 15% of 18,600 + 288 x 4.25


def test_the_blank_row_defaults_and_the_minimum_charge(db, estimate):
    """A box row from the page's blank: $30 a unit of equipment with a $300 floor (the tab's rows 38-40)."""
    from app.models.estimate_section import EstimateSection

    priced = mf.price_the_catalog(db)
    section = EstimateSection(estimate_id=estimate.id, **mf.SECTION)
    db.add(section)
    db.flush()
    few = MiscItem(section_id=section.id, description="a few", shape="box", unit="LF", qty=D("5"), unit_sale=D("100"),
                   labor_per_unit=D("150"), mix_design_id=priced["mix_id"], dim_a=D("48"), dim_b=D("36"), dim_c=D("8"),
                   concrete_waste=D("0.2"), steel_lb_per_cy=D("211.7"), forms_pct_of_concrete=D("0.5"),
                   super_pct_of_labor=D("1"), equip_per_unit=D("30"), equip_min=D("300"), sort_order=0)
    many = MiscItem(section_id=section.id, description="many", shape="box", unit="LF", qty=D("20"), unit_sale=D("100"),
                    labor_per_unit=D("150"), mix_design_id=priced["mix_id"], dim_a=D("48"), dim_b=D("36"), dim_c=D("8"),
                    concrete_waste=D("0.2"), steel_lb_per_cy=D("211.7"), forms_pct_of_concrete=D("0.5"),
                    super_pct_of_labor=D("1"), equip_per_unit=D("30"), equip_min=D("300"), sort_order=10)
    db.add_all([few, many])
    db.flush()
    from app.services.misc import refresh_section_misc_calcs

    refresh_section_misc_calcs(db, section)
    db.flush()
    refresh_pour_costs(db, section)
    assert D(str(few.calc_equip_cost)) == D("300.00") and D(str(many.calc_equip_cost)) == D("600.00")
    assert D(str(few.calc_super_cost)) == D(str(few.calc_labor_cost)) == D("750.00")


# ------------------------------------------------------------ the money --


def test_the_sale_is_typed_and_the_margin_is_the_answer(db, estimate):
    section = _build(db, estimate)
    row = _section(db, section.id)
    t = section_misc_totals(db, section.id, section)
    assert D(str(row["calc_total_sale"])) == mf.TOTAL_SALE == D(str(t["total_sale"]))
    assert D(str(t["total_margin"])) == ((mf.TOTAL_SALE - D(str(t["total_cost"]))) / mf.TOTAL_SALE).quantize(D("0.0001"))
    assert D(str(t["sale_at_markup"])) == (D(str(t["total_cost"])) * D("1.18")).quantize(D("0.01"))
    assert D(str(row["calc_total_sale"])) != (D(str(row["calc_total_cost"])) * D("1.18")).quantize(D("0.01"))
    assert t["item_count"] == 22 and t["row_count"] == 22
    assert row["unit"] == "LS"


def test_the_material_list(db, estimate):
    section = _build(db, estimate)
    m = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    assert set(m) == {"concrete", "rebar"}
    assert m["rebar"]["unit_cost"] == D("0.6000") and "PIERS" in m["rebar"]["detail"]


def test_the_total_and_every_cent_of_the_variance(db, estimate):
    """
    The app against the tab at these quantities. Two departures, named:

      * the tab ROUNDS each round base's and each block's yards UP and its
        steel to the pound, and reads pi as 3.145; the app keeps decimals
      * the tab forgot the tax on the round bases' and the blocks' concrete,
        steel and forms; the app taxes every purchase

    plus the gate track's 10 lb of extra bar once against per unit, and the
    ADA ramp's steel as a ratio of the concrete dollars against 211.7 lb/CY.
    """
    section = _build(db, estimate)
    row = _section(db, section.id)
    assert D(str(row["calc_total_cost"])) == mf.GOLDEN_COST
    assert D(str(row["calc_total_sale"])) == mf.TOTAL_SALE

    tab_total = sum((mf.tab_row(c, q)["cost"] for c, q in mf.QUANTITIES.items()), D("0"))
    exact_total = sum((mf.tab_row(c, q, exact=True)["cost"] for c, q in mf.QUANTITIES.items()), D("0"))
    # The app is its own exact structure to within the rows' cents.
    assert abs(D(str(row["calc_total_cost"])) - exact_total) <= D("0.25"), (row["calc_total_cost"], exact_total)
    # And the named departures are the whole gap to the tab.
    assert abs((D(str(row["calc_total_cost"])) - tab_total) - (exact_total - tab_total)) <= D("0.25")
    assert not [x for x in row["calc_unpriced"] if "mobilization" not in x], row["calc_unpriced"]


# ----------------------------------------------------------------- API --


def test_one_familys_grid_saves_without_touching_the_others(client, db, estimate):
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "miscellaneous", "name": "Misc"})
    sid = r.json()["id"]
    mix = client.get("/api/mix-designs").json()[0]["id"]
    rows = client.get(f"/api/misc-items?section_id={sid}").json()
    round_rows = [x for x in rows if x["shape"] == "round"]
    # Type ten light pole bases and add a round row from the page's blank.
    light = next(x for x in round_rows if x["code"] == "1301")
    payload = [{"id": light["id"], "shape": "round", "qty": 10, "mix_design_id": mix, "code": "1301",
                "description": "Light Pole Bases", "unit": "EA", "unit_sale": 1150, "labor_per_unit": 350,
                "dim_a": 24, "dim_b": 8, "steel_lb_per_in_ft": 0.95, "forms_pct_of_sale": 0.1, "forms_per_unit": 37.5,
                "super_pct_of_labor": 0.2, "equip_per_unit": 139},
               {"shape": "round", "description": "Flag pole base", "unit": "EA", "qty": 2, "unit_sale": 900,
                "labor_per_unit": 300, "mix_design_id": mix, "dim_a": 30, "dim_b": 10, "steel_lb_per_in_ft": 0.95,
                "forms_pct_of_sale": 0.1, "forms_per_unit": 37.5, "super_pct_of_labor": 0.2, "equip_per_unit": 155}]
    r = client.put("/api/misc-items/bulk", json={"section_id": sid, "rows": payload})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1 and body["updated"] == 1 and body["deleted"] == 0
    assert len(body["rows"]) == 23, "the other three families are untouched"
    saved = {x["code"]: x for x in body["rows"] if x["code"]}
    assert D(saved["1301"]["calc_sale"]) == 11500 and D(saved["1301"]["calc_cost"]) > 0
    assert saved["1301"]["calc_margin"] is not None
    new = next(x for x in body["rows"] if x["description"] == "Flag pole base")
    assert new["shape"] == "round" and D(new["calc_sale"]) == 1800 and D(new["calc_concrete_cy"]) > 0
    assert body["totals"]["item_count"] == 2 and D(body["totals"]["total_sale"]) == 13300

    # A quantity with no mix is a bought yard with no price: the section says so.
    r = client.put("/api/misc-items/bulk", json={"section_id": sid, "rows": [
        {"id": next(x["id"] for x in rows if x["code"] == "1310"), "shape": "block", "qty": 2},
    ]})
    assert r.status_code == 200, r.text
    sec = client.get(f"/api/sections/{sid}").json()
    assert any("mix" in x for x in sec["calc_unpriced"]), sec["calc_unpriced"]

    # The three line sets are empty on this kind, and it reads no rates.
    assert client.get(f"/api/sections/{sid}/forming-materials").json()["lines"] == []
    assert client.get(f"/api/sections/{sid}/labor").json()["lines"] == []
    assert client.get(f"/api/sections/{sid}/equipment").json()["lines"] == []
    assert client.get(f"/api/sections/{sid}/rates").json()["rows"] == []

    # Delete the new row: 22 again, and the job follows.
    assert client.delete(f"/api/misc-items/{new['id']}").status_code == 204
    assert len(client.get(f"/api/misc-items?section_id={sid}").json()) == 22
