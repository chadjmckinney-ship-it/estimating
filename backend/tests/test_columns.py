"""
Columns, against the sheet it was built from (sql/045).

07-COLUMNS is 68 cast-in-place columns in four types — 7,716 SF of form
contact, 47,417 lb of steel, 128.27 CY. The sheet reads **$160,746.20** and the
app reads **$172,300.84**, +7.19%, and the last test names every dollar of it.

That gap is large on purpose. Three of the four differences are the app
correcting the sheet, and the biggest one — form area — moves not just the
forming cost but the basis every shared dollar on the section is spread by.

## Three things here look wrong and are not

1. FORM AREA IS ALL FOUR FACES. Walls form ONE face and the wall sheet halves
   its contact area to say so. A column is wrapped, so nothing is halved, and
   the $/SF rates are correspondingly smaller — $2.50 forming here against the
   wall sheet's $3.50/FF.

2. SUPERVISION COMES FROM A COUNT, ON A FIVE-DAY WEEK. Not an area, and not
   seven days. 68 / 20 x 5 = 17. Every other assembly does one of the other
   two things.

3. TIE STEEL BILLS EVERY POUND. As on piers and walls — a column cage has no
   support-steel allowance to carve out.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.column_type import ColumnType
from app.services import columns as cl
from app.services.costing import allocation_basis, refresh_pour_costs
from app.services.columns import section_column_totals, super_days
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from tests import columns_fixture as cf

SHEET = cf.SHEET

APP = {
    "form_sf": Decimal("7716.0000"),
    "concrete_cy": Decimal("128.2666"),
    "steel_lb": Decimal("47417.079"),
    "chamfer_lf": Decimal("4368.000"),
    "super_days": Decimal("17.0000"),
    "direct": Decimal("53267.76"),
    "allocated": Decimal("105421.35"),   # −$18: SLAB CHAIRS $27, not METAL CHAIRS $45 (audit #7)
    "fuel": Decimal("6142.50"),
    "tax": Decimal("7449.74"),
    "total_cost": Decimal("172281.35"),
    "total_sale": Decimal("203291.99"),
    "cost_per_column": Decimal("2533.5493"),
}


@pytest.fixture
def columns(db, estimate):
    section = cf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def forming(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, sid)["lines"]}


def labor(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, sid)["lines"]}


def equipment(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, sid)["lines"]}


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------


def test_the_takeoff_totals(db, columns):
    t = section_column_totals(db, columns.id)
    assert t["column_count"] == 68
    assert t["type_count"] == 4
    assert t["total_form_sf"] == APP["form_sf"]
    assert t["total_concrete_cy"] == APP["concrete_cy"]
    assert t["total_rebar_lb"] == APP["steel_lb"]
    assert t["total_chamfer_lf"] == APP["chamfer_lf"]


def test_form_area_is_the_perimeter_not_the_cross_section(db, columns):
    """
    The sheet computes `height x (L x W / 36) / 2`, which multiplies the two
    plan dimensions where wrapping a column adds them. It is light by an amount
    that MOVES WITH THE SHAPE — 85.7% of the honest figure on an 18x24 and
    93.8% on an 18x30 — so it is not even a consistent convention like the wall
    sheet's halving.

    The sheet already holds the right expression in its own column X ("Build
    up") and spends it on exactly one labor line.
    """
    # One 18x24 column, 12 ft.
    assert cl.form_sf(12, 18, 24, 1) == Decimal("84.0000")
    assert cl.sheet_form_sf(12, 18, 24, 1) == Decimal("72.0000")
    # The distortion is shape-dependent, which is the tell.
    assert cl.form_sf(12, 18, 30, 1) == Decimal("96.0000")
    assert cl.sheet_form_sf(12, 18, 30, 1) == Decimal("90.0000")

    t = section_column_totals(db, columns.id)
    assert t["total_form_sf"] - SHEET["form_sf"] == Decimal("1056.0000")


def test_chamfer_counts_the_columns(db, columns):
    """
    `S81 = SUM(F10:F53) * 4` sums the HEIGHT column across the four TYPES and
    never multiplies by quantity. 240 LF on a 68-column job. Four corners of
    every column, full height, is 4,368.
    """
    t = section_column_totals(db, columns.id)
    assert t["total_chamfer_lf"] == Decimal("4368.000")
    # (12 + 24 + 12 + 12) x 4 — what the sheet actually computes.
    assert SHEET["chamfer_lf"] == Decimal("240")
    assert forming(db, columns.id)["chamfer"]["qty"] == Decimal("4368.0000")


def test_waste_reaches_the_main_vertical_bars(db, columns):
    """
    The sheet's bracket closes after vertical set 1, so its 10% lands on sets 2
    and 3, the ties and the dowels — every bar except the biggest one in the
    cage. Here it lands on all of them.

    Checked on the geometry rather than the total, so a change in bar weights
    cannot mask a change in the waste rule.
    """
    row = db.scalars(
        select(ColumnType).where(
            ColumnType.section_id == columns.id, ColumnType.label == "C1"
        )
    ).first()
    assert row is not None
    # 38 columns x 8 #8 bars x 12 ft x 2.670 lb/ft (ASTM) x 1.10 waste
    assert Decimal(str(row.calc_vert_rebar_lb)) == Decimal("10714.176")
    # Without the waste the sheet misses, the same bars are 9,740.16 lb.
    assert (
        Decimal(str(row.calc_vert_rebar_lb)) / Decimal("1.10")
    ).quantize(Decimal("0.001")) == Decimal("9740.160")


def test_the_sheet_can_still_be_reproduced(db, estimate):
    """
    `sheet_mode` restores the workbook's bar constants and its cross-section
    form area, so the bid can be reproduced deliberately rather than
    approximately.

    It does NOT restore the missing vertical-bar waste or the chamfer bug —
    those are decisions, not options, and a mode that quietly undid them would
    make the decisions invisible.
    """
    section = cf.build(db, estimate, sheet_mode=True)
    t = section_column_totals(db, section.id)
    assert t["total_form_sf"] == SHEET["form_sf"]
    # The only gap left is the waste the sheet does not apply: +2,479.13 lb.
    assert t["total_rebar_lb"] - SHEET["steel_lb"] == Decimal("2479.1317")


def test_concrete_keeps_its_decimals(db, columns):
    """The sheet ROUNDUPs each type to a whole CY — right for ordering trucks."""
    t = section_column_totals(db, columns.id)
    assert t["total_concrete_cy"] == Decimal("128.2666")
    assert SHEET["concrete_cy"] - t["total_concrete_cy"] == Decimal("1.7334")


# --------------------------------------------------------------------------
# the third supervision model
# --------------------------------------------------------------------------


def test_supervision_is_a_count_on_a_five_day_week(db, columns):
    """
    The first assembly to derive a duration from a COUNT, and the first on a
    five-day week:

        mono slab   SF / 16,000 x 7
        paving      SF / 25,000 x 7
        piers       typed
        columns     68 / 20 x 5 = 17
    """
    assert super_days(db, columns.id, "columns") == Decimal("17.0000")
    ln = labor(db, columns.id)
    assert ln["superintendent"]["qty"] == Decimal("17.0000")
    # The sheet puts a foreman on for every superintendent day (D93 = D92).
    assert ln["foreman"]["qty"] == Decimal("17.0000")
    assert ln["expense"]["qty"] == Decimal("17.0000")
    assert ln["pm"]["qty"] == Decimal("17.0000")


def test_the_equipment_ladder_rides_those_days(db, columns):
    """17 super days -> 30 rental days -> 9 billable, the same tier paving uses."""
    eq = equipment(db, columns.id)
    assert eq["skytrack"]["days_qty"] == Decimal("30.0000")
    assert eq["hoisting"]["ext_cost"] == Decimal("4275.00")   # 475 x 9
    assert eq["skid_steer"]["ext_cost"] == Decimal("2925.00")  # 325 x 9
    assert eq["storage"]["ext_cost"] == Decimal("945.00")      # 105 x 9


def test_tie_steel_bills_every_pound(db, columns):
    """No support-steel allowance on a column cage, as on piers and walls."""
    ln = labor(db, columns.id)
    t = section_column_totals(db, columns.id)
    assert ln["tie_steel"]["qty"] == (
        Decimal(str(t["total_rebar_lb"])) / Decimal("2000")
    ).quantize(Decimal("0.0001"))


def test_the_allocation_basis_is_form_area(db, columns):
    """
    Measured in EA, allocated by SF. A 24-foot column is not the same share of
    a supervisor as a 12-foot one, but the assembly is still quoted per column.
    """
    assert allocation_basis("columns") == "SF"
    rows = db.scalars(
        select(ColumnType).where(ColumnType.section_id == columns.id)
    ).all()
    # C2 is 23 columns of twice C1's height: fewer columns, more allocated cost.
    by_label = {r.label: r for r in rows}
    assert by_label["C2"].calc_allocated_cost > by_label["C1"].calc_allocated_cost


def test_there_is_no_footing_line(db, columns):
    """A column lands on someone else's footing. Pricing one here bills twice."""
    assert "footings" not in labor(db, columns.id)


# --------------------------------------------------------------------------
# the total
# --------------------------------------------------------------------------


def test_cost_blocks(db, columns):
    t = section_column_totals(db, columns.id)
    assert t["total_direct_cost"] == APP["direct"]
    assert t["total_allocated_cost"] == APP["allocated"]
    assert t["total_equip_fuel"] == APP["fuel"]
    assert t["total_tax"] == APP["tax"]


def test_the_total(db, columns):
    assert columns.calc_total_cost == APP["total_cost"]
    assert columns.calc_total_sale == APP["total_sale"]
    t = section_column_totals(db, columns.id)
    assert t["total_cost_per_unit"] == APP["cost_per_column"]


def test_every_dollar_of_the_difference_from_the_sheet(db, columns):
    """
    $172,300.84 against the sheet's $160,746.20 — **+$11,554.64, +7.19%**.

    Large, and every dollar of it accounted for. Three of the four causes are
    the app correcting the sheet; one is the sheet being sensible about
    ordering concrete and the app being sensible about costing it.

      +4,752.00  FORM AREA on the four labor lines. 1,056 more SF at $4.50
                 combined. BUILD-UP is not in here — the sheet already drives
                 that one off the honest figure.
      +3,235.27  FORM AREA on the lumber. Plywood is most of it: 33 more
                 sheets at $74.75, because you wrap four faces per column.
      +1,823.21  STEEL. The waste the sheet's bracket misses, plus ASTM bar
                 weights against its (size/16)^2 x 10.680159.
      +  583.01  TIE LABOR on that same steel, at $450/ton.
      +   56.10  ACCESSORIES on it, at $0.02/lb.
      +1,117.14  CHAMFER, 240 LF -> 4,368. The sheet forgets the count.
      +  183.49  MISCELLANEOUS EQUIPMENT. The sheet exempts that one line from
                 fuel and tax; here it is an ordinary rental. Same quirk the
                 slab, piers and wall reconciliations all found.
      +  122.39  THREE UNTAXED CELLS. Accessories (W99), form release (W105)
                 and chairs are computed `=S*U` where every neighbour reads
                 `=S*U*(1+tax)`. Same bug as the paving cure and siding lines.
      -  363.04  CONCRETE. The sheet ROUNDUPs each type to a whole CY; 1.7334
                 CY of concrete and the pumping that rides it.
      +   27.00  CHAIRS, which the sheet carries at no price at all. (SLAB
                 CHAIRS at $27 — until 2026-09-02 this line bought METAL
                 CHAIRS at $45 because it asked for "CHAIRS"; audit #7.)
    """
    t = section_column_totals(db, columns.id)
    f = forming(db, columns.id)
    tax = Decimal("1.0825")

    # 1. form area, and what rides it
    dsf = Decimal(str(t["total_form_sf"])) - SHEET["form_sf"]
    assert dsf == Decimal("1056.0000")
    labor_sf = dsf * Decimal("4.50")          # forming + place + wreck + rub
    lumber = (
        (Decimal("3858") - Decimal("3330")) * Decimal("0.859375")
        + (Decimal("241.125") - Decimal("208.125")) * Decimal("74.75")
        + Decimal("68.2")                      # one more box of 16p
    ) * tax

    # 2. steel: the waste the sheet misses, plus ASTM weights
    dlb = Decimal(str(t["total_rebar_lb"])) - SHEET["steel_lb"]
    steel = dlb * Decimal("0.65") * tax
    tie_labor = dlb / Decimal("2000") * Decimal("450")
    acc = dlb * Decimal("0.02") * tax

    # 3. chamfer
    chamfer = (Decimal("4368") - Decimal("240")) * Decimal("0.25") * tax
    assert f["chamfer"]["qty"] == Decimal("4368.0000")

    # 4. the sheet's exemptions and omissions
    misc_equip = Decimal("315") * Decimal("0.5825")
    untaxed = (
        Decimal("896.52") + Decimal("542") + Decimal("27")
    ) * Decimal("0.0825")
    chairs = Decimal("27")

    # 5. concrete, the one where the sheet is the sensible one
    dcy = Decimal(str(t["total_concrete_cy"])) - SHEET["concrete_cy"]
    concrete = dcy * Decimal("175") * tax + dcy * Decimal("20")

    named = (
        labor_sf + lumber + steel + tie_labor + acc + chamfer
        + misc_equip + untaxed + chairs + concrete
    )
    actual = Decimal(str(t["total_cost"])) - SHEET["total_cost"]

    assert abs(actual - named) < Decimal("0.75"), (
        f"variance {actual} is no longer the {named} this test accounts for — "
        "something changed that nobody has named"
    )
    pct = (Decimal(str(t["total_cost"])) / SHEET["total_cost"] - 1) * 100
    assert pct < Decimal("7.5")
