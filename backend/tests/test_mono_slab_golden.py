"""
04-PT Slab on Grade — the golden number, finally asserted.

**$671,712.66** cost / **$772,469.56** sale, 62,723 SF at $10.7092.

Why this file exists, in one paragraph: that number was reconciled against the
workbook on 2026-08-30, written into `claude/lbj-workbook-reconciliation.md`,
and asserted nowhere. The catalog was frozen at LBJ bid prices to protect it —
a hold maintained by a document and an intention. On 2026-08-31 two equipment
day rates were edited in the catalog, the section moved $4,984.91, and all 248
tests passed. It cost a morning to establish that nothing was actually broken.

The fixture states its own prices, so this test does not care what the catalog
holds. That is the whole point: the golden number is now pinned by something
that fails, and the catalog is free to carry current pricing again.

## Read this before "fixing" a failure here

A failure means one of two things and they are not the same:

  * a **quantity** moved — the takeoff is derived differently than it was, and
    that is a real regression until proven otherwise
  * a **cost block** moved while quantities held — a rate or a rule changed

The block assertions below exist so the failure output tells you which. Do not
update the constants to match new output without establishing which of the two
happened; the number's only value is that it was checked against the workbook
once, by hand.

## The 8 cents

This reads $671,712.66 where the reconciliation doc says $671,712.74. The
difference is a fix, not a drift: supervision days used to quantize weeks to
four decimals and *then* multiply by 7, a double round. 62,723 / 16,000 =
3.92019 weeks; the old path gave 27.4414 days, the honest one gives 27.4413,
and one ten-thousandth of a day across the superintendent ($425), expense
($100) and PM ($200) lines is 8 cents.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.mono_slab import MonoSlab
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.calc import section_mono_totals
from tests import mono_slab_fixture as mf

Q = mf.GOLDEN_QTY
C = mf.GOLDEN_COST


@pytest.fixture
def slab_section(db, estimate):
    section = mf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def pours(db, sid) -> list[MonoSlab]:
    return list(
        db.query(MonoSlab).filter_by(section_id=sid).order_by(MonoSlab.sort_order).all()
    )


def labor_lines(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, sid)["lines"]}


def equip_lines(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, sid)["lines"]}


def _dec(x) -> Decimal:
    return Decimal(str(x))


# --------------------------------------------------------------------------
# quantities — the takeoff
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(Q))
def test_quantity(db, slab_section, field):
    """
    Every derived quantity, one assertion each so the failure names the field.

    These are the numbers that were checked against the workbook by hand. A
    change here is a regression until somebody proves otherwise.
    """
    totals = section_mono_totals(db, slab_section.id)
    assert _dec(totals[field]) == Q[field]


def test_the_grade_beams_carry_no_bar_except_where_they_should(db, slab_section):
    """
    GB 1 and GB 2 are PT grade beams — the tendons reinforce them, and Chad
    confirmed the only loose steel is the #3 supporting cables and mat. The
    workbook's schedule for those sections was a support allowance folded into
    a beam type, which is where its phantom ~44,000 lb of rebar came from.

    If this ever fails with beam steel going UP, check that before believing it.
    """
    totals = section_mono_totals(db, slab_section.id)
    assert _dec(totals["total_grade_beam_rebar_lb"]) == Decimal("15381.503")
    assert _dec(totals["total_support_rebar_lb"]) == Decimal("6272.300")


# --------------------------------------------------------------------------
# money, block by block
# --------------------------------------------------------------------------


def test_direct_materials(db, slab_section):
    """Concrete, sand, steel, PT, poly and tape sitting on the pours."""
    total = sum(_dec(p.calc_direct_cost) for p in pours(db, slab_section.id))
    assert total == C["direct"]


def test_concrete_prices_at_the_bid_mix(db, slab_section):
    """2,205.1955 CY at $134 — the single largest material on the job."""
    totals = section_mono_totals(db, slab_section.id)
    cy = _dec(totals["total_concrete_cy"])
    assert (cy * mf.MIX_UNIT_COST).quantize(Decimal("0.01")) == Decimal("295496.20")


def test_forming_package(db, slab_section):
    assert _dec(load_stored_forming(db, slab_section.id)["total_ext_cost"]) == C["forming"]


def test_labor_and_supervision(db, slab_section):
    stored = load_stored_labor(db, slab_section.id)
    assert _dec(stored["total_labor_cost"]) == C["labor"]
    assert _dec(stored["total_supervision_cost"]) == C["supervision"]


def test_supervision_days_are_rounded_once(db, slab_section):
    """
    62,723 / 16,000 = 3.92019 weeks, x7, quantized ONCE.

    Quantizing weeks to four decimals first and then multiplying by 7 gives
    27.4414 and costs 8 cents across the three lines that ride these days. That
    double round is the entire difference between this test and the
    $671,712.74 in the reconciliation doc.
    """
    lines = labor_lines(db, slab_section.id)
    assert _dec(lines["superintendent"]["qty"]) == mf.SUPER_DAYS
    assert _dec(lines["expense"]["qty"]) == mf.SUPER_DAYS
    assert _dec(lines["pm"]["qty"]) == mf.SUPER_DAYS
    assert _dec(lines["superintendent"]["ext_cost"]) == Decimal("11662.55")
    assert _dec(lines["expense"]["ext_cost"]) == Decimal("2744.13")
    assert _dec(lines["pm"]["ext_cost"]) == Decimal("5488.26")


def test_tie_steel_bills_tied_steel_only(db, slab_section):
    """
    Support steel holds cables and mat up while the crew works; nobody ties it
    as reinforcing. 21,944.977 lb total less 6,272.300 support = 15,672.677 lb,
    7.8363 tons at $400.
    """
    lines = labor_lines(db, slab_section.id)
    assert _dec(lines["tie_steel"]["qty"]) == Decimal("7.8363")
    assert _dec(lines["tie_steel"]["ext_cost"]) == Decimal("3134.52")


def test_brick_ledge_labor_exists(db, slab_section):
    """830 LF at $1.00 — a line the workbook has no equivalent for."""
    lines = labor_lines(db, slab_section.id)
    assert _dec(lines["brick_ledge"]["qty"]) == Decimal("830")
    assert _dec(lines["brick_ledge"]["ext_cost"]) == Decimal("830.00")


def test_equipment_rentals_and_services_are_separate(db, slab_section):
    """
    Rentals carry fuel & maintenance and tax; pumping is a service and carries
    neither. Splitting them by GROUP rather than by the unit string was a phase-3
    fix — a crew day rate is priced per day and is not a rental.
    """
    stored = load_stored_equipment(db, slab_section.id)
    assert _dec(stored["total_equipment_cost"]) == C["equipment_rental"]
    assert _dec(stored["total_contract_cost"]) == C["equipment_contract"]


def test_the_two_rates_that_drifted(db, slab_section):
    """
    MINI EXCAVATOR at $475 and SKID STEER at $225, both 18 days.

    These are the two the catalog quietly moved to $250 and $275 on 2026-08-31,
    which cost $4,984.91 and a morning. Pinned here so the catalog can hold
    current prices without this section noticing.
    """
    lines = equip_lines(db, slab_section.id)
    assert _dec(lines["mini_excavator"]["ext_cost"]) == Decimal("8550.00")
    assert _dec(lines["skid_steer"]["ext_cost"]) == Decimal("4050.00")


def test_fuel_and_tax(db, slab_section):
    ps = pours(db, slab_section.id)
    assert sum(_dec(p.calc_equip_fuel) for p in ps) == C["fuel"]
    assert sum(_dec(p.calc_tax) for p in ps) == C["tax"]


# --------------------------------------------------------------------------
# the number itself
# --------------------------------------------------------------------------


def test_the_golden_total(db, slab_section):
    assert _dec(slab_section.calc_total_cost) == C["total_cost"]
    assert _dec(slab_section.calc_total_sale) == C["total_sale"]
    assert _dec(slab_section.calc_cost_per_unit) == C["cost_per_sf"]


def test_the_blocks_add_up_to_the_total(db, slab_section):
    """
    Direct + takeoffs + fuel + tax, with nothing unaccounted for.

    This is the assertion that makes the block tests above useful: if one block
    moves and the total still matches, something is being counted twice.
    """
    parts = (
        C["direct"]
        + C["forming"]
        + C["labor"]
        + C["supervision"]
        + C["equipment_rental"]
        + C["equipment_contract"]
        + C["fuel"]
        + C["tax"]
    )
    assert parts == C["total_cost"]
    assert _dec(slab_section.calc_total_cost) == parts


def test_the_pours_sum_to_the_section(db, slab_section):
    """No pour carries cost the section does not, and none is left out."""
    ps = pours(db, slab_section.id)
    assert sum(_dec(p.calc_cost) for p in ps) == _dec(slab_section.calc_total_cost)
    assert sum(_dec(p.calc_sale) for p in ps) == _dec(slab_section.calc_total_sale)


def test_the_fixture_owns_its_prices(db, slab_section):
    """
    The catalog can hold anything. Change a price after the fixture has built
    and the section must not move until it is re-costed from the new price —
    which is what frees claude/price-restore-checklist.md to finally be applied.
    """
    from sqlalchemy import text

    before = _dec(slab_section.calc_total_cost)
    db.execute(text("UPDATE equipment SET unit_cost = 999 WHERE name = 'SKID STEER'"))
    db.flush()
    assert _dec(slab_section.calc_total_cost) == before
