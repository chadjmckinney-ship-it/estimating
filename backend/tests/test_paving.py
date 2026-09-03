"""
Paving, against the sheet it was built from (sql/036, phase 3).

10-PAVING in the LBJ workbook is a filled paving section Chad copied in from
another job so the app would have real numbers to build against: 272,703 SF in
three areas, taxable at 8.25%, marked up 18%, totalling $1,327,183.47.

This file rebuilds that sheet out of the app's own parts — the seeded catalog
at LBJ bid prices, a paving section, three pours — and checks what comes out.
The app reads **$1,335,789.97**, which is $8,606.50 over the sheet, and the
last test in this file accounts for every cent of the difference. Four of the
five causes are the sheet being wrong. The fifth is a real question about a
catalog price, and it is worth more than the other four put together.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.mono_slab import MonoSlab
from app.services import paving as pv
from app.services.calc import section_mono_totals
from app.services.costing import refresh_pour_costs, resolve_rebar
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from tests import paving_fixture as pf

# What the app produces. Written out rather than derived so that a change to
# any rule moves a number here and has to be explained.
APP = {
    "total_cost": Decimal("1339045.84"),
    "total_sale": Decimal("1580074.10"),
    "total_tax": Decimal("74388.36"),
    "concrete_cy": Decimal("4832.4125"),
    "edge_concrete_cy": Decimal("93.6039"),
    "sand_cy": Decimal("1784.3530"),
    "steel_lb": Decimal("150386.615"),
    "supervision": Decimal("40087.32"),
}


@pytest.fixture
def paving(db, estimate):
    """The whole sheet: a priced mix, a paving section, three areas, costed."""
    section = pf.build(db, estimate)
    # Order matters — forming and labor feed the drivers equipment rides on,
    # and all three feed the cost allocation.
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def forming(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, section_id)["lines"]}


def labor(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, section_id)["lines"]}


def equipment(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, section_id)["lines"]}


# --------------------------------------------------------------------------
# quantities
# --------------------------------------------------------------------------


def test_paving_concrete_includes_the_curb(db, paving):
    """
    (SF × thick / 324 + curb / 108 + thick_edge × 1.5 × 0.18 / 27) × (1 + waste)

    The curb is a quarter of a cubic foot per linear foot, and on 9,537 LF of
    it that is 93.6 CY — about two percent of the pour, and all of it invisible
    if paving is priced with the slab formula.
    """
    t = section_mono_totals(db, paving.id)
    assert t["total_sf"] == Decimal("272703.000")
    assert t["total_curb_lf"] == Decimal("9537.000")
    assert t["total_edge_concrete_cy"] == APP["edge_concrete_cy"]
    assert t["total_concrete_cy"] == APP["concrete_cy"]
    # The sheet reads 4,832.4124; the app rounds the two halves separately.
    assert abs(t["total_concrete_cy"] - pf.SHEET["concrete_cy"]) <= Decimal("0.0002")


def test_paving_sand_matches_the_sheet_exactly(db, paving):
    t = section_mono_totals(db, paving.id)
    assert t["total_sand_cy"] == pf.SHEET["sand_cy"] == APP["sand_cy"]


def test_paving_carries_no_support_steel_and_no_vapor_barrier(db, paving):
    """
    Both would have been silent additions.

    Support steel at the company's 0.1 lb/SF is 27,270 lb of #3 nobody buys —
    that allowance exists to hold cables and mat up over a beam cage, and a
    paving mat sits on chairs, which are already a line of their own. The vapor
    barrier is worse: the paving sheet has no poly line at all, so the app
    would have been pricing 300,000 SF of wrap against a rollup that never
    mentions it.
    """
    t = section_mono_totals(db, paving.id)
    assert t["total_support_rebar_lb"] == Decimal("0.000")
    assert t["total_poly_sf"] == Decimal("0.000")
    assert t["total_rebar_lb"] == t["total_slab_bar_lb"] == APP["steel_lb"]


def test_the_joint_layout(db, paving):
    """
    Construction joints at 60 ft; control joints at 15 ft both ways, less the
    construction joints already cut. Six lines are priced off these two
    numbers, which is why they are computed in one place.
    """
    joints = pv.joints_for(pf.TOTAL_SF)
    assert joints.construction_lf == pf.SHEET["construction_joint_lf"] == 4546
    assert joints.control_lf == pf.SHEET["control_joint_lf"] == 31815

    e = equipment(db, paving.id)
    assert e["joint_construction"]["days_qty"] == Decimal("4546.0000")
    assert e["joint_control"]["days_qty"] == Decimal("31815.0000")
    assert e["soft_cut"]["days_qty"] == Decimal("31815.0000")
    saw_cutting = sum(
        e[c]["ext_cost"] for c in ("joint_construction", "joint_control", "soft_cut")
    )
    assert saw_cutting == pf.SHEET["saw_cutting"] == Decimal("42270.10")


# --------------------------------------------------------------------------
# forming — the structural difference
# --------------------------------------------------------------------------


def test_paving_forms_off_curb_not_perimeter(db, paving):
    """
    The single biggest difference between the two sheets. Every lumber line on
    10-PAVING reads SUM(I10:I34) — the curb column — where the slab sheet reads
    the pour perimeter. These areas have no perimeter entered at all, so a
    paving section priced with the slab line set would have formed for free.
    """
    f = forming(db, paving.id)
    for code in ("2x4", "2x6", "2x10"):
        assert f[code]["qty"] == Decimal("9537.0000"), code
    assert f["stakes"]["qty"] == Decimal("381.0000")  # round(2x10 / 25)
    assert f["siding"]["qty"] == Decimal("18.0000")  # roundup(curb × 0.03 / 16)


def test_paving_nails_run_three_times_as_far(db, paving):
    """One box of 16p per 1,500 LF of curb, against the slab sheet's 500."""
    f = forming(db, paving.id)
    assert f["16p"]["qty"] == Decimal("8.0000")  # roundup(9537 × 1.25 / 1500)
    assert f["8p"]["qty"] == Decimal("4.0000")  # roundup(9537 × 1.25 / 3000)
    assert f["6p"]["qty"] == f["8p"]["qty"]


def test_sealant_board_splits_on_thickness(db, paving):
    """
    A 1x6 in anything 8" and under, a 1x8 over it, and the tack strip runs the
    total. All three areas here are thin, so the 1x8 is zero — the sheet gets
    the same answer by hard-coding it, which stops being right the first time a
    job pours a 10" pad.
    """
    f = forming(db, paving.id)
    assert f["rw6"]["qty"] == Decimal("4546.0000")
    assert f["rw8"]["qty"] == Decimal("0.0000")
    assert f["tack_strip"]["qty"] == Decimal("4546.0000")


def test_paving_cure_covers_more_ground(db, paving):
    """350 SF/gal outdoors against the slab sheet's 300: 15 drums, not 17."""
    f = forming(db, paving.id)
    assert f["cure"]["qty"] == Decimal("15.0000")
    assert pv.cure_drums(pf.TOTAL_SF) == 15
    assert f["cure"]["ext_cost"] == pf.SHEET["cure"] == Decimal("8512.50")


def test_accessories_come_from_the_catalog(db, paving):
    """
    $0.04/lb — the catalog's ACCESSORIES, same as every other assembly.

    Until sql/044 an `accessories_unit_cost` row said paving bought the same
    item at $0.02, which read as a genuine assembly difference. It was not: the
    row was seeded from `10-PAVING!T80`, a cell that types 0.02 over its own
    `Pricing!Q14` lookup — and Pricing says 0.04. One of six typed-over price
    cells in that workbook. The row is gone and the line asks the catalog.
    """
    f = forming(db, paving.id)
    assert f["accessories"]["qty"] == APP["steel_lb"]
    assert f["accessories"]["unit_cost"] == Decimal("0.0400")


def test_haul_off_is_the_one_untaxed_line(db, paving):
    """
    Hauling is work done, not a thing bought. It sits in the lumber block
    because that is where the sheet's author put it; it is the only line in
    that block the app agrees should not be taxed.
    """
    f = forming(db, paving.id)
    assert f["haul_off"]["taxable"] is False
    assert [c for c, ln in f.items() if not ln["taxable"]] == ["haul_off"]


# --------------------------------------------------------------------------
# labor, supervision, equipment
# --------------------------------------------------------------------------


def test_paving_labor_is_exactly_a_dollar_a_foot(db, paving):
    """$0.30 forming + $0.55 place and finish + $0.15 wreck, on every SF."""
    ln = labor(db, paving.id)
    assert ln["forming"]["ext_cost"] == Decimal("81810.90")
    assert ln["place_finish"]["ext_cost"] == Decimal("149986.65")
    assert ln["wreck"]["ext_cost"] == Decimal("40905.45")
    total = sum(ln[c]["ext_cost"] for c in ("forming", "place_finish", "wreck"))
    assert total == pf.SHEET["labor"] == Decimal("272703.00")


def test_paving_supervises_one_man_and_no_pm(db, paving):
    """
    SF / 25,000 a week, seven days a week, one superintendent and his expense.
    No foreman, no project manager — the sheet carries both rows empty.

    Two cents under the sheet, and the reason is in the last test.
    """
    ln = labor(db, paving.id)
    assert ln["superintendent"]["qty"] == Decimal("76.3568")
    assert ln["foreman"]["qty"] == Decimal("0.0000")
    assert ln["pm"]["qty"] == Decimal("0.0000")
    assert ln["pm"]["rate"] == Decimal("200.0000")  # the rate is real; the days are not
    supervision = ln["superintendent"]["ext_cost"] + ln["expense"]["ext_cost"]
    assert supervision == APP["supervision"]
    assert pf.SHEET["supervision"] - supervision == Decimal("0.02")


def test_the_equipment_ladder_bills_36_of_120_days(db, paving):
    """
    76.36 superintendent days put the ladder at 120 rental days, and the tier
    rule bills 120 / 30 × 9 = 36 of them. A Bob Cat, a light tower and a vault.
    """
    e = equipment(db, paving.id)
    for code in ("bobcat", "light_tower", "vault"):
        assert e[code]["days_qty"] == Decimal("120.0000"), code
        assert e[code]["billable_units"] == Decimal("36.0000"), code
    rentals = sum(e[c]["ext_cost"] for c in ("bobcat", "light_tower", "vault"))
    assert rentals == Decimal("15840.00")
    # Fuel & maintenance at 50% and tax at 8.25% both ride the same base:
    # 15,840 × 1.5825 = 25,066.80, which is what the sheet's rollup reads.
    assert (rentals * Decimal("1.5825")).quantize(Decimal("0.01")) == pf.SHEET["equipment"]


def test_a_contract_service_priced_by_the_day_burns_no_diesel(db, paving):
    """
    Out-of-town expense is a man-day, not a machine day. Costing tells them
    apart by group, so a day-rate line in the contract group carries neither
    fuel & maintenance nor sales tax.
    """
    e = equipment(db, paving.id)
    assert e["out_of_town"]["group_name"] == "contract"
    assert e["barricades"]["group_name"] == "contract"


# --------------------------------------------------------------------------
# the grid save
# --------------------------------------------------------------------------


def test_a_grid_save_recalculates_the_section_once(db, paving):
    """
    Twenty-five areas across sixteen columns is a table, not a form. Saving it
    a field at a time would re-run forming, labor and equipment on every
    keystroke, because all three key off the section totals.
    """
    from app.services.pours import bulk_save_pours

    first = (
        db.query(MonoSlab)
        .filter_by(section_id=paving.id)
        .order_by(MonoSlab.sort_order)
        .first()
    )
    counts = bulk_save_pours(db, paving, [{"id": first.id, "curb_lf": Decimal("7000")}])
    assert counts == {"created": 0, "updated": 1, "deleted": 0}

    t = section_mono_totals(db, paving.id)
    assert t["total_curb_lf"] == Decimal("9971.000")  # 7000 + 2882 + 89
    # And the forming package followed the curb without being asked.
    assert forming(db, paving.id)["2x4"]["qty"] == Decimal("9971.0000")


def test_a_grid_save_will_not_silently_drop_a_row(db, paving):
    """
    Sending back fewer rows than the section has is not a delete. The grid can
    scroll, a filter can hide a row, a request can be truncated — and none of
    those should cost an area.
    """
    from app.services.pours import bulk_save_pours

    bulk_save_pours(db, paving, [])
    assert section_mono_totals(db, paving.id)["slab_count"] == 3

    bulk_save_pours(db, paving, [], delete_missing=True)
    assert section_mono_totals(db, paving.id)["slab_count"] == 0


def test_a_new_grid_row_needs_the_two_fields_nothing_works_without(db, paving):
    from app.services.pours import BulkSaveError, bulk_save_pours

    with pytest.raises(BulkSaveError, match="square_footage"):
        bulk_save_pours(db, paving, [{"curb_lf": Decimal("100")}])


# --------------------------------------------------------------------------
# the total, and every cent of the difference
# --------------------------------------------------------------------------


def test_the_section_totals(db, paving):
    assert paving.calc_quantity == Decimal("272703.000")
    assert paving.calc_total_tax == APP["total_tax"]
    assert paving.calc_total_cost == APP["total_cost"]
    assert paving.calc_total_sale == APP["total_sale"]
    # 18% markup, taken on cost.
    # Sale is the SUM of per-area sales, so it can sit a cent off the section
    # total times the factor — each area rounds once. Asserting equality here
    # passed for months by luck and broke the first time an area's cents moved.
    assert abs(
        (paving.calc_total_cost * Decimal("1.18")).quantize(Decimal("0.01"))
        - APP["total_sale"]
    ) <= Decimal("0.02")


def test_paving_pays_full_sales_tax(db, paving):
    """
    Not exempt. This section is the direct evidence for never defaulting
    tax_exempt from the section kind: it is paving, inside a job, paying 8.25%.
    Only ROW paving is exempt, and nothing about the word "paving" says which.
    """
    assert paving.tax_exempt is None
    assert paving.calc_total_tax == APP["total_tax"]


def test_every_cent_of_the_difference_from_the_sheet(db, paving):
    """
    $1,339,045.84 against the sheet's $1,327,183.47 — $11,862.37 over. Six
    causes, all settled:

      +15,943.22  3/4" smooth dowels. The sheet types $1.90 a piece straight
                  into the cell. RESOLVED 2026-09-01: `Pricing!P50/Q50` in that
                  same workbook carries "3/4" x 24" smooth dowels" at exactly
                  $4.995 — the app's own figure, from Chad's own price list.
                  `10-PAVING!T90` had been typed over; reconnected, the sheet
                  agrees. An earlier note here guessed the $4.995 was "an
                  assembly with cap and basket"; that was invented, and wrong.

       +3,253.41  ACCESSORIES at the catalog's $0.04. The sheet types $0.02 at
                  `10-PAVING!T80` over its own `Pricing!Q14` lookup, which
                  reads $0.04. The app carried the same $0.02 in an
                  assembly_rates row copied from that cell until sql/044.

       -8,133.51  Steel at $0.50/lb. The sheet types $0.55; the catalog has a
                  REBAR PAVING line at $0.50 and the app prices from the
                  catalog. Also needs a decision, but the app is doing the
                  right thing by asking the catalog rather than a cell.

         +702.28  Cure taxed. The sheet's cure cell reads `=T*R` where its
          +29.70  neighbours read `=T*R*(1+tax)`, and so does its siding cell.
                  Both are purchased materials. Two more of the same bug sit on
                  concrete haul-off, which really is a service and stays
                  untaxed here, and on form release, whose quantity is zero.

          +61.61  Steel weight. The app weighs #3 bar at the ASTM 0.376 lb/ft
          + 4.93  the whole system uses; the sheet computes 0.3757154 from
                  (size/16)^2 × 10.6870159. 113.8 lb across 272,703 SF, and the
                  accessories line rides the same tonnage.

           +0.77  Lumber: catalog prices are stored to four decimals where the
                  workbook's Pricing sheet carries six (2x6 at 1.4453 against
                  1.4453125).

           -0.03  Rounding, in three places: superintendent days stored to four
                  decimals (76.3568 against 76.35684), tie wire rolls likewise,
                  and per-pour cents on concrete and sand.
    """
    f = forming(db, paving.id)
    tax = Decimal("1.0825")

    # 1. the dowels — the one that needs a decision
    dowels = f["smooth_dowels"]
    assert dowels["qty"] == Decimal("4546.0000")
    assert dowels["unit_cost"] == Decimal("4.9950")
    assert "3/4" in (dowels["material_name"] or "")
    sheet_dowels = Decimal("4546") * Decimal("1.90")  # typed on the sheet, untaxed
    assert (dowels["ext_cost"] * tax - sheet_dowels).quantize(
        Decimal("0.01")
    ) == Decimal("15943.22")

    # 2. the steel price — catalog against sheet. Resolved through the
    # section's book (sql/048), which on this fixture carries the catalog's
    # own numbers.
    from app.services.price_book import priced_as

    with priced_as(db, paving.estimate_id):
        rebar = resolve_rebar(db, False, "paving")
    assert rebar["name"] == "REBAR PAVING"
    assert rebar["unit_cost"] == Decimal("0.5000")
    price_gap = (
        pf.SHEET["steel_lb"]
        * (Decimal("0.50") - pf.SHEET["steel_rate"])
        * tax
    ).quantize(Decimal("0.01"))
    assert price_gap == Decimal("-8133.51")

    # 3 + 4. two cells the sheet forgot to tax
    assert f["cure"]["taxable"] is True
    assert f["siding"]["taxable"] is True
    untaxed_on_the_sheet = f["cure"]["ext_cost"] + f["siding"]["ext_cost"]
    assert (untaxed_on_the_sheet * (tax - 1)).quantize(Decimal("0.01")) == Decimal(
        "731.98"
    )

    # 5. and the bar weight the app is right about
    weight_gap = APP["steel_lb"] - pf.SHEET["steel_lb"]
    assert weight_gap.quantize(Decimal("0.001")) == Decimal("113.829")
    weight_money = (
        weight_gap * (Decimal("0.50") + Decimal("0.04")) * tax
    ).quantize(Decimal("0.01"))
    assert weight_money == Decimal("66.54")  # 61.61 steel + 4.93 accessories

    # 6. accessories, now that the rate is the catalog's on both sides
    acc_rate_gap = (
        pf.SHEET["steel_lb"] * (Decimal("0.04") - Decimal("0.02")) * tax
    ).quantize(Decimal("0.01"))
    assert acc_rate_gap == Decimal("3253.41")

    # The named causes, added up. What is left is the four-decimal storage the
    # last two entries of the docstring describe.
    named = (
        Decimal("15943.22")  # dowels
        + Decimal("-8133.51")  # steel price
        + Decimal("731.98")  # cure + siding tax
        + acc_rate_gap
        + weight_money
    )
    residual = paving.calc_total_cost - pf.SHEET["total_cost"] - named
    assert residual == Decimal("0.73")  # +0.77 lumber precision, -0.03 rounding

    # The whole difference, to the cent.
    assert paving.calc_total_cost - pf.SHEET["total_cost"] == Decimal("11862.37")
