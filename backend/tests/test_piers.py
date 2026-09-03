"""
Piers, against the sheet it was built from (sql/037).

01-Piers is 106 drilled shafts in six groups — 2,348 LF, 632.70 CY,
$283,953.00 at 18% markup. It is the first assembly in this system that is not
a pour and the first whose unit is EA, which is why the allocation tests below
matter more than the arithmetic ones.

The app reads **$285,225.89**, +0.45%, and the last test accounts for it.

Both figures dropped $11,648.21 / $11,978.64 on 2026-09-01 (sql/043). Pier steel
was priced at $0.75/lb from `01-Piers!G53` — a cell whose `Pricing` lookup had
been typed over with a constant. Reconnected, it reads **$0.60**: the same
REBAR PIERS / PT slabs a post-tensioned slab buys. Quantities did not move.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.pier_group import PierGroup
from app.services import piers as pv
from app.services import price_book as pb
from app.services.costing import allocation_basis, refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.piers import section_pier_totals
from tests import piers_fixture as pf

APP = {
    "total_cost": Decimal("285225.89"),
    "total_sale": Decimal("336566.55"),
    "total_tax": Decimal("12377.07"),
    "concrete_cy": Decimal("632.7784"),
    "steel_lb": Decimal("73771.453"),
    "vert_lb": Decimal("56428.390"),
    "tie_lb": Decimal("11738.800"),
    "dowel_lb": Decimal("5604.263"),
}


@pytest.fixture
def piers(db, estimate):
    section = pf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    # Typed last, the way a person does it: open the section, then say how long
    # the job is. The equipment ladder has to follow on its own from here.
    pf.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def forming(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, sid)["lines"]}


def labor(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, sid)["lines"]}


def equipment(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, sid)["lines"]}


def groups(db, sid) -> list[PierGroup]:
    return list(
        db.query(PierGroup).filter_by(section_id=sid).order_by(PierGroup.sort_order).all()
    )


# --------------------------------------------------------------------------
# the allocation basis — the reason piers needed more than a table
# --------------------------------------------------------------------------


def test_piers_allocate_by_count_not_area(db, piers):
    """
    The bug this exists to prevent.

    Shared cost is spread across a section's rows weighted by SF. A pier has
    none, and `allocate_amount` falls back to "the last row takes the
    remainder" when every weight is zero — so on the SF basis the entire
    forming, labor and equipment cost would land on whichever group sorted
    last, with no error and nothing on screen to notice.

    Two of these six groups are the same pier in different quantities: 12 and 4
    shafts, both 24" x 21'. Priced per pier they must come out identical.
    """
    assert allocation_basis("piers") == "EA"
    assert allocation_basis("mono_slab") == allocation_basis("paving") == "SF"

    gs = groups(db, piers.id)
    assert [g.qty for g in gs] == [12, 12, 46, 20, 4, 12]

    # Every group carries a share. Under the old basis, five would be zero.
    assert all(g.calc_allocated_cost > 0 for g in gs)

    twelve, four = gs[1], gs[4]
    assert (twelve.qty, four.qty) == (12, 4)
    assert twelve.diameter_in == four.diameter_in
    assert twelve.calc_total_depth_ft == four.calc_total_depth_ft
    assert twelve.calc_cost_per_unit == four.calc_cost_per_unit
    # ...and three times the piers costs three times as much.
    assert twelve.calc_cost == (four.calc_cost * 3).quantize(Decimal("0.01"))


def test_the_section_is_measured_in_piers(db, piers):
    assert piers.unit == "EA"
    assert piers.calc_quantity == Decimal("106.000")
    assert piers.calc_cost_per_unit == (
        APP["total_cost"] / Decimal("106")
    ).quantize(Decimal("0.0001"))


# --------------------------------------------------------------------------
# the cage
# --------------------------------------------------------------------------


def test_the_hole(db, piers):
    t = section_pier_totals(db, piers.id)
    assert t["pier_count"] == pf.SHEET["piers"] == 106
    assert t["total_lf"] == pf.SHEET["total_lf"] == Decimal("2348.000")
    assert t["total_concrete_cy"] == APP["concrete_cy"]
    # 0.0125% over the sheet, which is real pi against its 3.1412.
    assert abs(t["total_concrete_cy"] - pf.SHEET["concrete_cy"]) < Decimal("0.09")


def test_the_tie_formula_that_looks_wrong_and_is_not(db):
    """
    The sheet multiplies a hoop circumference in INCHES by a depth in FEET over
    a spacing in INCHES. The two twelves cancel; it is right. Written honestly
    here so nobody corrects it into a 12x error.
    """
    import math

    # 46-pier group: 36" shaft, 24 ft, #3 ties at 10", 1.5" cover, no hook.
    sheet = (Decimal("3") / 16) ** 2 * Decimal("10.680159") * (
        (Decimal("36") - 3) * Decimal("3.1412")
    ) * Decimal("24") / Decimal("10")
    honest = (
        pv.tie_count(Decimal("24"), Decimal("10"))
        * Decimal("0.375474")  # (3/16)^2 x 10.680159, the sheet's lb/ft
        * (Decimal("33") * Decimal(str(math.pi)) / 12)
    )
    # Same to a tenth of a pound on 4,297 lb — the residue is pi, not units.
    assert abs(sheet - honest) < Decimal("0.6")


def test_the_confinement_band_is_a_count_not_a_length(db, piers):
    """
    "3 #3 stirrups at 3 inches top" — the drawing says a count at a spacing, so
    that is what the model takes. The band's own depth comes off the run below
    it so the top nine inches are not counted twice.
    """
    # 24 ft at 10" is 28.8 ties; the band replaces the top 9" with 3.
    plain = pv.tie_count(Decimal("24"), Decimal("10"))
    banded = pv.tie_count(Decimal("24"), Decimal("10"), 3, Decimal("3"))
    assert plain == Decimal("28.800")
    assert banded == Decimal("30.900")  # 3 + (24 - 0.75) x 12 / 10
    assert banded > plain

    g = groups(db, piers.id)[2]
    assert g.calc_tie_count == Decimal("30.900")


def test_steel_splits_into_bars_ties_and_dowels(db, piers):
    t = section_pier_totals(db, piers.id)
    assert t["total_vert_rebar_lb"] == APP["vert_lb"]
    assert t["total_tie_rebar_lb"] == APP["tie_lb"]
    assert t["total_dowel_rebar_lb"] == APP["dowel_lb"]
    assert t["total_rebar_lb"] == APP["steel_lb"]
    # The hook and the band are the whole of the difference from the sheet.
    assert t["total_rebar_lb"] - pf.SHEET["steel_lb"] == Decimal("2034.973")


def test_verticals_are_cut_to_length(db, piers):
    """
    No lap and no bottom cover: Chad's cages are cut to length and field tied,
    so waste_rebar here is genuinely waste. On a slab mat the same column
    carries the lap — same field, two meanings, decided by the assembly.
    """
    g = groups(db, piers.id)[2]  # 46 @ 36" x 24 ft, 8 #8
    expected = (
        Decimal("8") * Decimal("2.670") * Decimal("24") * Decimal("46") * Decimal("1.10")
    )
    assert g.calc_vert_rebar_lb == expected.quantize(Decimal("0.001"))


# --------------------------------------------------------------------------
# drilling
# --------------------------------------------------------------------------


def test_drilling_comes_from_the_rate_table(db, piers):
    """
    The sheet's $58,032 "PIER QUOTE" is not a quote — it is a $/LF rate table
    by diameter, summed. 564 LF of 24" at $8 + 1,104 of 36" at $30 + 680 of 42"
    at $30.
    """
    t = section_pier_totals(db, piers.id)
    assert t["total_drill_cost"] == pf.SHEET["drilling"] == Decimal("58032.00")
    assert t["groups_without_drill_rate"] == 0

    rates = {int(g.diameter_in): g.calc_drill_lf_rate for g in groups(db, piers.id)}
    assert rates[24] == Decimal("8.0000")
    assert rates[36] == Decimal("30.0000")
    assert rates[42] == Decimal("30.0000")


def test_an_unpriced_diameter_says_so_rather_than_guessing(db, piers):
    """
    A diameter with no row in the table prices at nothing and reports itself.
    Interpolating a drilling rate across 2,348 LF is a five-figure error with
    nothing on screen to notice.
    """
    g = groups(db, piers.id)[0]
    g.diameter_in = Decimal("39")  # not in the table
    pv.refresh_pier_group_calcs(db, g, piers)
    db.flush()

    with pb.priced_as(db, piers.estimate_id):
        assert pv.drill_rate(db, Decimal("39")) is None
    assert g.calc_drill_lf_rate is None
    assert g.calc_drill_cost is None
    assert section_pier_totals(db, piers.id)["groups_without_drill_rate"] == 1


def test_drilling_is_never_taxed(db, piers):
    """Drilling a shaft is work, not a purchase."""
    from app.services.costing import cost_units

    units = cost_units(db, piers)
    assert sum(u.direct_untaxed for u in units) == pf.SHEET["drilling"]
    # Tax is charged on materials only: concrete and steel.
    taxable = sum(u.direct_taxable for u in units)
    assert (taxable * Decimal("0.0825")).quantize(Decimal("0.01")) <= piers.calc_total_tax


# --------------------------------------------------------------------------
# labor, supervision, equipment
# --------------------------------------------------------------------------


def test_pier_labor_is_priced_by_the_pier(db, piers):
    ln = labor(db, piers.id)
    for code in ("layout", "place_finish", "cleanup"):
        assert ln[code]["qty"] == Decimal("106.0000"), code
        assert ln[code]["unit"] == "/EA"
        assert ln[code]["ext_cost"] == Decimal("5300.00"), code
    # No area rates at all on this assembly.
    assert not any(l["unit"] == "/SF" for l in ln.values())
    # And every pound is tied — a pier cage has no support-steel allowance.
    assert ln["tie_steel"]["qty"] == (
        APP["steel_lb"] / Decimal("2000")
    ).quantize(Decimal("0.0001"))


def test_supervision_days_are_typed_and_the_ladder_follows(db, piers):
    """
    Piers has no area, so no duration can be derived. Somebody types the days,
    and the equipment ladder has to move with them — which is the part that
    would silently not happen.
    """
    ln = labor(db, piers.id)
    assert ln["superintendent"]["qty"] == Decimal("15.0000")
    assert ln["foreman"]["qty"] == Decimal("10.0000")
    assert ln["pm"]["qty"] == Decimal("10.0000")
    supervision = ln["superintendent"]["ext_cost"] + ln["foreman"]["ext_cost"]
    assert supervision == pf.SHEET["supervision"] == Decimal("8875.00")
    assert ln["pm"]["ext_cost"] == pf.SHEET["pm"] == Decimal("2000.00")

    # 15 typed days -> ladder -> 21 rental days -> tier -> 9 billable.
    eq = equipment(db, piers.id)
    for code in ("skid_steer", "light_tower", "vault", "misc_equip"):
        assert eq[code]["days_qty"] == Decimal("21.0000"), code
        assert eq[code]["billable_units"] == Decimal("9.0000"), code


def test_changing_the_days_moves_the_equipment(db, piers):
    from app.services.labor import update_labor_line

    update_labor_line(db, piers.id, "superintendent", qty=Decimal("30"), mark_manual=True)
    eq = equipment(db, piers.id)
    # 30 days -> ladder 7 + 53 = 60 -> tier (60/30) x 9 = 18 billable.
    assert eq["skid_steer"]["days_qty"] == Decimal("60.0000")
    assert eq["skid_steer"]["billable_units"] == Decimal("18.0000")


def test_contract_services_ride_concrete_and_count(db, piers):
    eq = equipment(db, piers.id)
    t = section_pier_totals(db, piers.id)
    assert eq["surveying"]["days_qty"] == Decimal("106.0000")
    assert eq["surveying"]["ext_cost"] == Decimal("2650.00")
    assert eq["concrete_pump"]["days_qty"] == t["total_concrete_cy"]
    # Spoil swells 30% coming out of the hole.
    assert eq["haul_off"]["days_qty"] == (
        t["total_concrete_cy"] * Decimal("1.3")
    ).quantize(Decimal("0.0001"))


# --------------------------------------------------------------------------
# lumber
# --------------------------------------------------------------------------


def test_pier_lumber_runs_off_counts_and_steel(db, piers):
    """Not one line on this sheet is driven by a perimeter or an area."""
    f = forming(db, piers.id)
    assert f["2x4"]["qty"] == f["2x6"]["qty"] == Decimal("848.0000")   # piers x 8
    assert f["stakes"]["qty"] == Decimal("9.0000")                      # ceil(106/12.5)
    assert f["16p"]["qty"] == Decimal("5.0000")                         # ceil(steel/15000)
    assert f["pier_sleds"]["qty"] == Decimal("880.5000")                # LF/8 x 3
    assert f["pier_boots"]["qty"] == Decimal("424.0000")                # piers x 4
    assert f["accessories"]["qty"] == APP["steel_lb"]
    assert f["haul_off"]["taxable"] is False  # hauling is a service
    assert f["cure"]["taxable"] is True       # unlike the paving sheet's slip


# --------------------------------------------------------------------------
# the total
# --------------------------------------------------------------------------


def test_the_section_totals(db, piers):
    assert piers.calc_total_cost == APP["total_cost"]
    assert piers.calc_total_tax == APP["total_tax"]
    assert piers.calc_total_sale == APP["total_sale"]
    assert (
        piers.calc_total_cost * Decimal("1.18")
    ).quantize(Decimal("0.01")) == APP["total_sale"]


def test_every_cent_of_the_difference_from_the_sheet(db, piers):
    """
    $285,225.89 against $283,953.00 — +$1,272.89, +0.45%. Four causes:

      +1,322  steel. The 12" tie hook and the 3 #3 confinement ties at the top,
              both asked for, both absent from the sheet: +2,034.97 lb at
              $0.60. Real pi on the hoop is a few cents of that.
      + 458  tie labor on that same extra steel, at $450/ton.
      - 547  lumber. Pier sleds are $2.25 in the catalog against the $2.75
              the sheet types, and boots $3.00 against $3.25 — today's prices,
              below the 2002 bid. Concrete haul-off also stops being taxed,
              because hauling is a service.
      +  26  equipment. The sheet exempts the vault and miscellaneous from fuel
              and tax and bills miscellaneous flat; both are ordinary rentals
              here.
      +  15  real pi instead of 3.1412, on concrete and on pumping.
    """
    t = section_pier_totals(db, piers.id)
    f = forming(db, piers.id)
    tax = Decimal("1.0825")

    # 1. the steel Chad asked for
    extra_lb = t["total_rebar_lb"] - pf.SHEET["steel_lb"]
    assert extra_lb == Decimal("2034.973")
    steel_money = (extra_lb * pf.SHEET["steel_rate"] * tax).quantize(Decimal("0.01"))
    tie_labor = (extra_lb / Decimal("2000") * Decimal("450")).quantize(Decimal("0.01"))
    assert steel_money == Decimal("1321.71")
    assert tie_labor == Decimal("457.87")

    # 2. catalog prices below the sheet's typed ones
    assert f["pier_sleds"]["unit_cost"] == Decimal("2.2500")   # sheet types 2.75
    assert f["pier_boots"]["unit_cost"] == Decimal("3.0000")   # sheet types 3.25

    # 3. and the whole of it
    assert piers.calc_total_cost - pf.SHEET["total_cost"] == Decimal("1272.89")
    pct = (piers.calc_total_cost / pf.SHEET["total_cost"] - 1) * 100
    assert pct < Decimal("0.6")
