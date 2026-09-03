"""
The drilling quote (sql/038).

sql/037 shipped estimate_sections.pier_drill_quote with a comment promising it
replaced the rate table, and nothing read the column. A number typed there
changed nothing and warned nobody. These tests exist so that cannot come back.

Drilling is the largest single line on a pier job — $58,032 of LBJ's $211,441
direct cost — and in the field it is a hard number from the drilling sub. The
rate table is the placeholder until that number arrives.

Two properties matter more than the arithmetic:

  * the quote is apportioned by LF and the shares sum to it exactly, because
    piers cost out per pier and a lump dropped on the section makes every
    per-pier figure below it wrong
  * a quote priced against one takeoff and left sitting over a different one
    says so, loudly — the failure this system keeps producing is a stale stored
    number with nothing on screen to notice
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.pier_group import PierGroup
from app.services import piers as pv
from app.services import price_book as pb
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.piers import section_pier_totals
from tests import piers_fixture as pf

# What pier_drill_rates charges for the LBJ takeoff, to the dollar.
RATE_TABLE_DRILLING = Decimal("58032.00")

# A plausible quote from a driller: under the table, as they often are once
# they have seen the logs.
QUOTE = Decimal("54500.00")


@pytest.fixture
def piers(db, estimate):
    section = pf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    pf.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def groups(db, sid) -> list[PierGroup]:
    return list(
        db.query(PierGroup).filter_by(section_id=sid).order_by(PierGroup.sort_order).all()
    )


def set_quote(db, section, amount, *, stamp=True):
    """Write a drilling quote the way the router does — value, then LF baseline."""
    from app.models.section_quote import SectionQuote
    from app.services import quotes as qt

    row = db.query(SectionQuote).filter_by(section_id=section.id, kind="drilling").one_or_none()
    if amount is None or amount <= 0:
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            row = SectionQuote(section_id=section.id, kind="drilling")
            db.add(row)
        row.amount = amount
        row.unit = "LS"
        row.baseline_qty = (
            qt.section_driver_qty(db, section, "drilling") if stamp else None
        )
        row.baseline_unit = "LF" if stamp else None
    db.flush()
    pv.refresh_section_pier_calcs(db, section)
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()


# --------------------------------------------------------------------------
# no quote — the table still governs
# --------------------------------------------------------------------------


def test_no_quote_uses_the_rate_table(db, piers):
    """The state every job starts in, and plenty get bid in."""
    t = section_pier_totals(db, piers.id)
    assert t["drill_source"] == "rates"
    assert t["total_drill_cost"] == RATE_TABLE_DRILLING
    assert t["drill_quote"] is None
    assert t["drill_quote_stale"] is False


def test_zero_is_a_cleared_field_not_free_drilling(db, piers):
    """
    Nobody drills 2,348 LF for nothing. A 0 in the box is somebody emptying it,
    so it falls back to the table rather than pricing the largest line at zero.
    """
    set_quote(db, piers, Decimal("0"))
    t = section_pier_totals(db, piers.id)
    assert t["drill_source"] == "rates"
    assert t["total_drill_cost"] == RATE_TABLE_DRILLING


def test_quote_is_ignored_off_a_piers_section(db, estimate):
    """The column is on every section. It only means anything on one kind."""
    from app.models.estimate_section import EstimateSection

    s = EstimateSection(
        estimate_id=estimate.id, kind="mono_slab", name="slab", unit="SF",
        margin_pct=Decimal("0.15"), contingency_pct=Decimal("0"),
    )
    db.add(s)
    db.flush()
    # A drilling quote is not even offered on a slab, and would not be read.
    assert "drilling" not in __import__(
        "app.services.quotes", fromlist=["kinds_for"]
    ).kinds_for("mono_slab")
    assert pv.drill_quote(s, db) is None


# --------------------------------------------------------------------------
# the spread — the part the sheet's J54 does not do
# --------------------------------------------------------------------------


def test_quote_replaces_the_table(db, piers):
    set_quote(db, piers, QUOTE)
    t = section_pier_totals(db, piers.id)
    assert t["drill_source"] == "quote"
    assert t["total_drill_cost"] == QUOTE
    assert t["drill_quote"] == QUOTE


def test_shares_sum_to_the_quote_exactly(db, piers):
    """
    allocate_amount gives the last group the remainder, so six shares of an
    awkward number still add up. A rounding crumb here is a cent that shows on
    the bid and never reconciles.
    """
    odd = Decimal("54321.77")
    set_quote(db, piers, odd)
    assert sum(g.calc_drill_cost for g in groups(db, piers.id)) == odd


def test_spread_follows_the_rate_tables_shape(db, piers):
    """
    Not a flat per-foot split. The table charges $8/LF for a 24" shaft and
    $30/LF for a 42" one, so spreading a lump evenly by LF would price small
    piers at nearly three times their cost and large ones at a discount. The
    quote sets the level; the table's relative weights set the distribution.
    """
    set_quote(db, piers, QUOTE)
    gs = groups(db, piers.id)
    assert section_pier_totals(db, piers.id)["drill_quote_basis"] == "rate_shape"

    ratio = QUOTE / RATE_TABLE_DRILLING
    for g in gs:
        with pb.priced_as(db, piers.estimate_id):
            table = pv.drill_rate(db, g.diameter_in) * Decimal(str(g.calc_total_lf))
        expected = (table * ratio).quantize(Decimal("0.01"))
        assert abs(Decimal(str(g.calc_drill_cost)) - expected) <= Decimal("0.05")


def test_flat_lf_is_only_the_fallback(db, piers):
    """
    When a diameter has no row the table cannot describe the shape, so the
    split falls back to plain LF — cruder, but it says so rather than
    zero-weighting the unpriced group and handing its drilling to the others.
    """
    g = groups(db, piers.id)[0]
    g.diameter_in = Decimal("38")
    db.flush()
    set_quote(db, piers, QUOTE)

    t = section_pier_totals(db, piers.id)
    assert t["drill_quote_basis"] == "lf"
    assert t["total_drill_cost"] == QUOTE
    gs = groups(db, piers.id)
    total_lf = sum(Decimal(str(x.calc_total_lf)) for x in gs)
    for x in gs:
        expected = (QUOTE * Decimal(str(x.calc_total_lf)) / total_lf).quantize(
            Decimal("0.01")
        )
        assert abs(Decimal(str(x.calc_drill_cost)) - expected) <= Decimal("0.05")
    # The unpriced group still gets paid for, which is the point.
    assert Decimal(str(gs[0].calc_drill_cost)) > 0


def test_effective_rate_is_the_quote_not_the_table(db, piers):
    """
    The grid keeps showing a $/LF under a quote — the share divided by the
    feet — so it stays sanity-checkable against the table it replaced.
    """
    set_quote(db, piers, QUOTE)
    for g in groups(db, piers.id):
        lf = Decimal(str(g.calc_total_lf))
        assert Decimal(str(g.calc_drill_lf_rate)) == (
            Decimal(str(g.calc_drill_cost)) / lf
        ).quantize(Decimal("0.0001"))


def test_quote_rescues_a_diameter_the_table_has_never_heard_of(db, piers):
    """
    A 38" shaft has no row in pier_drill_rates, so without a quote it prices at
    nothing and reports itself missing. Once a real number covers the hole, a
    missing table row is no longer a hole — the table only ever existed to
    guess until the quote arrived.
    """
    g = groups(db, piers.id)[0]
    g.diameter_in = Decimal("38")
    db.flush()
    pv.refresh_section_pier_calcs(db, piers)
    db.flush()
    t = section_pier_totals(db, piers.id)
    assert t["groups_without_drill_rate"] == 1
    assert t["drill_source"] == "rates"

    set_quote(db, piers, QUOTE)
    t = section_pier_totals(db, piers.id)
    assert t["groups_without_drill_rate"] == 0
    assert t["total_drill_cost"] == QUOTE
    # And the comparison is withheld, because a table total that skips a group
    # invites subtracting it from the quote and calling the difference a saving.
    assert t["drill_rate_cost"] is None


def test_clearing_the_quote_returns_to_the_table(db, piers):
    set_quote(db, piers, QUOTE)
    assert section_pier_totals(db, piers.id)["drill_source"] == "quote"
    set_quote(db, piers, None)
    t = section_pier_totals(db, piers.id)
    assert t["drill_source"] == "rates"
    assert t["total_drill_cost"] == RATE_TABLE_DRILLING


# --------------------------------------------------------------------------
# staleness — the only way this field can hurt you
# --------------------------------------------------------------------------


def test_a_fresh_quote_is_not_stale(db, piers):
    set_quote(db, piers, QUOTE)
    t = section_pier_totals(db, piers.id)
    assert t["drill_quote_lf"] == Decimal("2348.000")
    assert t["drill_quote_stale"] is False


def test_growing_the_takeoff_makes_the_quote_stale(db, piers):
    """
    The whole reason pier_drill_quote_lf exists. Add 8 piers after the driller
    quoted and the lump sum does not grow — but the screen has to say so, or
    2,348 LF of price silently covers 2,540 LF of holes.
    """
    set_quote(db, piers, QUOTE)
    g = groups(db, piers.id)[2]
    g.qty = g.qty + 8
    db.flush()
    pv.refresh_section_pier_calcs(db, piers)
    db.flush()

    t = section_pier_totals(db, piers.id)
    assert t["drill_quote_stale"] is True
    assert t["drill_quote_lf"] == Decimal("2348.000")
    assert t["total_lf"] > Decimal("2348.000")
    # The quote itself has NOT grown. That is correct — a quote is a quote —
    # which is exactly why the warning has to carry the weight.
    assert t["total_drill_cost"] == QUOTE


def test_recalc_never_restamps_the_baseline(db, piers):
    """
    If recalc re-stamped, the baseline would chase the takeoff and the warning
    could never fire. A warning that cannot trigger is worse than none, because
    the screen looks reassuring.
    """
    set_quote(db, piers, QUOTE)
    g = groups(db, piers.id)[0]
    g.qty = g.qty + 5
    db.flush()
    for _ in range(3):
        pv.refresh_section_pier_calcs(db, piers)
        db.flush()
    assert section_pier_totals(db, piers.id)["drill_quote_lf"] == Decimal("2348.000")
    assert section_pier_totals(db, piers.id)["drill_quote_stale"] is True


def test_an_unstamped_quote_reads_as_stale(db, piers):
    """
    A quote typed straight into the database, or carried over from before
    sql/038, has no baseline. That is not evidence it is current.
    """
    set_quote(db, piers, QUOTE, stamp=False)
    db.flush()
    t = section_pier_totals(db, piers.id)
    assert t["drill_quote_lf"] is None
    assert t["drill_quote_stale"] is True


# --------------------------------------------------------------------------
# what it does to the bid
# --------------------------------------------------------------------------


def test_the_comparison_is_the_estimators_check(db, piers):
    """What the table would have charged, shown next to what was quoted."""
    set_quote(db, piers, QUOTE)
    t = section_pier_totals(db, piers.id)
    assert t["drill_rate_cost"] == RATE_TABLE_DRILLING
    assert t["drill_quote"] == QUOTE


def test_drilling_stays_untaxed_under_a_quote(db, piers):
    """
    Drilling a shaft is work, not a purchase. Swapping the source of the number
    must not accidentally turn it into a taxable material.
    """
    before = section_pier_totals(db, piers.id)["total_tax"]
    set_quote(db, piers, QUOTE)
    assert section_pier_totals(db, piers.id)["total_tax"] == before


def test_the_saving_reaches_the_section_total(db, piers):
    """A cheaper quote has to actually make the job cheaper, by its own margin."""
    before = section_pier_totals(db, piers.id)["total_cost"]
    set_quote(db, piers, QUOTE)
    after = section_pier_totals(db, piers.id)["total_cost"]
    assert after == before - (RATE_TABLE_DRILLING - QUOTE)


def test_per_pier_costs_follow_the_quote(db, piers):
    """
    The reason the lump is spread at all: each group carries its own cost per
    pier, and those have to move when the drilling price does.
    """
    before = {g.id: g.calc_cost_per_unit for g in groups(db, piers.id)}
    set_quote(db, piers, QUOTE)
    after = {g.id: g.calc_cost_per_unit for g in groups(db, piers.id)}
    # Under the rate-table shape a cheaper quote scales every group's drilling
    # by the same ratio, so every group gets cheaper — no group subsidises
    # another, which is exactly what a flat LF split would have done.
    assert all(after[k] < before[k] for k in before)
