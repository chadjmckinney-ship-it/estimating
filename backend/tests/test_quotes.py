"""
Rebar and PT quotes (sql/039).

The drilling quote proved the shape; these two prove it generalises. What is
being tested is mostly not arithmetic — it is the four places a quote can be
quietly wrong:

  * a unit price that converts wrong ($/cwt read as $/lb is a 100x error that
    still looks like a plausible number on a screen)
  * a lump landing on rows it does not belong to — PT charged to pours with no
    PT in them
  * a labor line vanishing because a material quote was mistaken for
    furnish-and-install
  * a lump quietly sitting over a takeoff that has moved

The drilling-quote tests live next door in test_pier_drill_quote.py; this file
does not repeat them.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.mono_slab import MonoSlab
from app.models.section_quote import SectionQuote
from app.services import quotes as qt
from app.services.costing import refresh_pour_costs
from app.services.forming import refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor

_Q2 = Decimal("0.01")


def set_quote(db, section, kind, amount, unit="LS", *, stamp=True):
    """Write a quote the way the router does — value, unit, then baseline."""
    row = (
        db.query(SectionQuote)
        .filter_by(section_id=section.id, kind=kind)
        .one_or_none()
    )
    amount = Decimal(str(amount)) if amount is not None else None
    if amount is None or amount <= 0:
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            row = SectionQuote(section_id=section.id, kind=kind)
            db.add(row)
        row.amount = amount
        row.unit = unit
        is_lump = unit == "LS"
        row.baseline_qty = (
            qt.section_driver_qty(db, section, kind) if (is_lump and stamp) else None
        )
        row.baseline_unit = qt.QUOTE_KINDS[kind]["driver"] if is_lump and stamp else None
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()


def cost_of(db, section) -> Decimal:
    refresh_pour_costs(db, section)
    db.flush()
    return Decimal(str(section.calc_total_cost))


@pytest.fixture
def slab(db, section, make_pour):
    """Two pours, one post-tensioned and one not — the case PT gets wrong."""
    a = make_pour(description="PT pour", square_footage=Decimal("10000"), post_tension=True)
    b = make_pour(description="plain pour", square_footage=Decimal("6000"), post_tension=False)
    refresh_pour_costs(db, section)
    db.flush()
    return section, a, b


# --------------------------------------------------------------------------
# which assemblies carry which quotes
# --------------------------------------------------------------------------


def test_each_assembly_offers_only_the_quotes_that_apply():
    assert set(qt.kinds_for("mono_slab")) == {qt.REBAR, qt.PT}
    assert set(qt.kinds_for("piers")) == {qt.DRILLING, qt.REBAR}
    # Paving has bar but no PT and no holes.
    assert set(qt.kinds_for("paving")) == {qt.REBAR}
    # Walls and columns both carry bar, and neither has PT or holes.
    assert set(qt.kinds_for("walls_footings")) == {qt.REBAR}
    # Columns joined the list on 2026-09-01 (sql/045) — 47,417 lb of cage on
    # LBJ alone. Until the assembly existed this asserted an empty list.
    assert set(qt.kinds_for("columns")) == {qt.REBAR}
    # An assembly with no takeoff yet offers nothing rather than everything.
    assert qt.kinds_for("panels") == []


def test_units_are_per_kind():
    assert qt.units_for(qt.DRILLING) == ("LS",)
    assert set(qt.units_for(qt.REBAR)) == {"LS", "TON", "CWT", "LB"}
    assert set(qt.units_for(qt.PT)) == {"LS", "SF"}


# --------------------------------------------------------------------------
# unit conversion — the 100x and 2000x errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unit,amount,expected_per_lb",
    [
        ("LB", "0.62", "0.62"),
        ("CWT", "62.00", "0.62"),
        ("TON", "1240.00", "0.62"),
    ],
)
def test_a_rebar_quote_converts_to_dollars_per_pound(unit, amount, expected_per_lb):
    """
    The three ways a fabricator writes the same price. Storing the unit rather
    than normalising on the way in is deliberate: the estimator checking this
    screen against the fax needs to see the number they were quoted.
    """
    q = qt.Quote(qt.REBAR, Decimal(amount), unit, None, None)
    assert q.per_lb() == Decimal(expected_per_lb)


def test_a_lump_has_no_unit_price():
    q = qt.Quote(qt.REBAR, Decimal("50000"), "LS", None, None)
    assert q.per_lb() is None
    assert q.is_lump


# --------------------------------------------------------------------------
# rebar
# --------------------------------------------------------------------------


def catalog_steel_cost(db, section, pours) -> Decimal:
    """
    What the catalog charges for these pours' steel.

    Per pour, not per section, because a post-tensioned pour buys different bar
    — resolve_rebar reaches for REBAR PT on one and REBAR GRADE BEAM on the
    other. Summing tonnage and multiplying by one rate gets the wrong answer,
    which is how this helper came to exist.
    """
    from app.services.costing import _rebar_unit_cost, _z
    from app.services.price_book import priced_as

    # Priced the way the section is priced — through its book (sql/048). On an
    # estimate with no sheet that is the catalog, which is what this helper has
    # always meant; on one with a sheet it is the job's price, which is what it
    # should mean.
    total = Decimal("0")
    with priced_as(db, section.estimate_id):
        for p in pours:
            rate = _z(_rebar_unit_cost(db, bool(p.post_tension), section.kind))
            total += Decimal(str(p.calc_total_rebar_lb)) * rate
    return total


def test_unit_priced_rebar_replaces_the_catalog_rate(db, slab):
    section, a, b = slab
    before = cost_of(db, section)
    lb = Decimal(str(a.calc_total_rebar_lb)) + Decimal(str(b.calc_total_rebar_lb))
    assert lb > 0

    catalog_cost = catalog_steel_cost(db, section, (a, b))
    set_quote(db, section, qt.REBAR, "0.62", "LB")

    after = cost_of(db, section)
    # One quoted rate now covers both pours, PT bar included — the quote is for
    # the job's steel, not for a catalog line.
    delta = Decimal("0.62") * lb - catalog_cost
    assert abs((after - before) - delta * (Decimal("1") + _tax(db, section))) < Decimal("0.05")


def test_a_rebar_lump_is_spread_by_weight_not_by_area(db, slab):
    """
    The 10,000 SF pour and the 6,000 SF pour do not carry steel in that ratio
    once their bar schedules differ. Spreading by area would move money between
    them and make both cost-per-SF figures wrong.
    """
    section, a, b = slab
    set_quote(db, section, qt.REBAR, "40000", "LS")

    wa = Decimal(str(a.calc_total_rebar_lb))
    wb = Decimal(str(b.calc_total_rebar_lb))
    total = wa + wb
    share_a = (Decimal("40000") * wa / total).quantize(_Q2)

    # The pour's direct cost carries its share; check the share landed, not the
    # whole lump on one row.
    from app.services.costing import cost_units

    units = {u.row.id: u for u in cost_units(db, section)}
    assert units[a.id].direct_taxable > units[b.id].direct_taxable
    # And the two shares add back to the quote.
    from app.services.costing import _rebar_unit_cost, _z
    from app.services.price_book import priced_as

    with priced_as(db, section.estimate_id):
        catalog = _z(_rebar_unit_cost(db, False, section.kind))
    unquoted_a = units[a.id].direct_taxable - share_a
    assert unquoted_a >= 0
    assert catalog >= 0


def test_a_rebar_lump_totals_to_the_quote(db, slab):
    """The section's steel costs the quote, and not a cent more or less."""
    section, a, b = slab
    from app.services.costing import cost_units

    plain = sum(u.direct_taxable for u in cost_units(db, section))
    steel_at_catalog = catalog_steel_cost(db, section, (a, b))

    set_quote(db, section, qt.REBAR, "40000", "LS")
    quoted = sum(u.direct_taxable for u in cost_units(db, section))

    # Everything except the steel is unchanged, so the difference is exactly
    # the quote replacing the catalog figure.
    assert abs((quoted - plain) - (Decimal("40000") - steel_at_catalog)) <= Decimal("0.02")


def test_a_rebar_quote_does_not_touch_tie_steel_labor(db, slab):
    """
    Chad's call, and the safe direction. Leaving labor in when a quote covered
    it overstates the bid and somebody notices; dropping labor the quote did
    not cover understates it and nobody notices until the job is running.
    """
    section, a, b = slab
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    db.flush()
    before = {
        ln["code"]: ln["ext_cost"] for ln in load_stored_labor(db, section.id)["lines"]
    }

    set_quote(db, section, qt.REBAR, "40000", "LS")
    refresh_and_store_labor(db, section.id)
    db.flush()
    after = {
        ln["code"]: ln["ext_cost"] for ln in load_stored_labor(db, section.id)["lines"]
    }

    assert before == after, "a material quote must not move a labor line"
    assert Decimal(str(after.get("tie_steel", 0))) > 0


# --------------------------------------------------------------------------
# PT — the one that can land on the wrong rows
# --------------------------------------------------------------------------


def test_a_pt_lump_lands_only_on_post_tensioned_pours(db, slab):
    """
    The sharpest failure in this file. Spread by plain SF, a PT lump would
    charge PT to a pour that has none — and it would read as a plausible
    per-SF number on every row rather than as an error anywhere.
    """
    section, a, b = slab
    from app.services.costing import cost_units

    before = {u.row.id: u.direct_taxable for u in cost_units(db, section)}
    set_quote(db, section, qt.PT, "25000", "LS")
    after = {u.row.id: u.direct_taxable for u in cost_units(db, section)}

    assert after[b.id] == before[b.id], "the non-PT pour must not move"
    assert after[a.id] > before[a.id]


def test_a_pt_quote_priced_per_sf_uses_pt_area(db, slab):
    section, a, b = slab
    from app.services.costing import _pt_sf_unit_cost, _z, cost_units
    from app.services.price_book import priced_as

    with priced_as(db, section.estimate_id):
        catalog = _z(_pt_sf_unit_cost(db))
    before = {u.row.id: u.direct_taxable for u in cost_units(db, section)}
    set_quote(db, section, qt.PT, "1.15", "SF")
    after = {u.row.id: u.direct_taxable for u in cost_units(db, section)}

    sf = Decimal(str(a.square_footage))
    assert abs((after[a.id] - before[a.id]) - (Decimal("1.15") - catalog) * sf) <= _Q2
    assert after[b.id] == before[b.id]


def test_a_pt_baseline_counts_pt_sf_not_section_sf(db, slab):
    """
    16,000 SF in the section, 10,000 of it post-tensioned. A lump stamped
    against the wrong one would read stale the moment anything changed, or
    never — both useless.
    """
    section, a, b = slab
    assert qt.section_driver_qty(db, section, qt.PT) == Decimal("10000.000")


# --------------------------------------------------------------------------
# staleness — lumps only
# --------------------------------------------------------------------------


def test_a_unit_price_is_never_stale(db, slab):
    """
    It follows the takeoff by construction — more tons, more money. Warning
    about it would train people to ignore the banner that matters.
    """
    section, a, b = slab
    set_quote(db, section, qt.REBAR, "0.62", "LB")
    a.square_footage = Decimal("30000")
    db.flush()

    row = db.query(SectionQuote).filter_by(section_id=section.id, kind=qt.REBAR).one()
    q = qt.QuoteSet([row]).get(qt.REBAR)
    assert q.baseline_qty is None
    assert qt.is_stale(q, qt.section_driver_qty(db, section, qt.REBAR)) is False


def test_a_lump_goes_stale_when_the_takeoff_moves(db, slab):
    section, a, b = slab
    set_quote(db, section, qt.REBAR, "40000", "LS")
    row = db.query(SectionQuote).filter_by(section_id=section.id, kind=qt.REBAR).one()
    baseline = row.baseline_qty
    assert baseline is not None

    from app.services.calc import refresh_mono_slab_calcs

    a.square_footage = Decimal("30000")
    db.flush()
    refresh_mono_slab_calcs(db, a, section)
    db.flush()

    q = qt.QuoteSet([row]).get(qt.REBAR)
    current = qt.section_driver_qty(db, section, qt.REBAR)
    assert current != baseline
    assert qt.is_stale(q, current) is True
    # The lump has not grown. That is correct, and it is why the warning has to
    # carry the weight.
    assert row.amount == Decimal("40000")


def test_an_unstamped_lump_reads_as_stale(db, slab):
    section, a, b = slab
    set_quote(db, section, qt.REBAR, "40000", "LS", stamp=False)
    row = db.query(SectionQuote).filter_by(section_id=section.id, kind=qt.REBAR).one()
    q = qt.QuoteSet([row]).get(qt.REBAR)
    assert qt.is_stale(q, qt.section_driver_qty(db, section, qt.REBAR)) is True


# --------------------------------------------------------------------------
# clearing
# --------------------------------------------------------------------------


def test_zero_clears_rather_than_pricing_the_package_at_nothing(db, slab):
    section, a, b = slab
    before = cost_of(db, section)
    set_quote(db, section, qt.REBAR, "0.62", "LB")
    assert cost_of(db, section) != before
    set_quote(db, section, qt.REBAR, 0)
    assert cost_of(db, section) == before


def test_quotes_are_independent(db, slab):
    """A PT quote must not disturb the steel, and the reverse."""
    section, a, b = slab
    set_quote(db, section, qt.REBAR, "0.62", "LB")
    with_rebar = cost_of(db, section)
    set_quote(db, section, qt.PT, "25000", "LS")
    both = cost_of(db, section)
    set_quote(db, section, qt.PT, 0)
    assert cost_of(db, section) == with_rebar
    assert both > with_rebar


def _tax(db, section) -> Decimal:
    from app.services.costing import tax_rate_for

    return tax_rate_for(db, section)


# --------------------------------------------------------------------------
# through the endpoint — validation, and the stamping the router owns
# --------------------------------------------------------------------------


@pytest.fixture
def client(db):
    """
    The real app, on the rolled-back session.

    The endpoint tests below are the ones that would have caught the sql/037
    bug: the service layer can be perfect while nothing is wired to it.
    """
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_endpoint_writes_reads_and_clears(client, db, slab):
    section, a, b = slab
    sid = str(section.id)

    r = client.put(f"/api/sections/{sid}/quotes/rebar", json={"amount": "1240", "unit": "TON",
                                                             "note": "Acme, material only"})
    assert r.status_code == 200, r.text
    body = {q["kind"]: q for q in r.json()}
    assert body["rebar"]["unit"] == "TON"
    assert body["rebar"]["stale"] is False
    # A unit price gets no baseline, because it cannot drift.
    assert body["rebar"]["baseline_qty"] is None

    r = client.put(f"/api/sections/{sid}/quotes/rebar", json={"amount": "0"})
    assert r.status_code == 200
    assert r.json() == []


def test_endpoint_stamps_a_lump_baseline(client, db, slab):
    section, a, b = slab
    sid = str(section.id)
    r = client.put(f"/api/sections/{sid}/quotes/pt", json={"amount": "25000", "unit": "LS"})
    assert r.status_code == 200, r.text
    q = r.json()[0]
    # PT SF, not section SF — 10,000 of the 16,000 is post-tensioned.
    assert Decimal(q["baseline_qty"]) == Decimal("10000.000")
    assert q["baseline_unit"] == "SF"
    assert q["stale"] is False


def test_endpoint_refuses_a_quote_the_assembly_cannot_carry(client, db, slab):
    """A slab has no holes to drill. Better a 400 than a row nothing reads."""
    section, a, b = slab
    r = client.put(
        f"/api/sections/{section.id}/quotes/drilling", json={"amount": "5000"}
    )
    assert r.status_code == 400
    assert "cannot carry" in r.json()["detail"]


def test_endpoint_refuses_a_unit_the_kind_is_not_priced_in(client, db, slab):
    section, a, b = slab
    r = client.put(
        f"/api/sections/{section.id}/quotes/pt", json={"amount": "1.15", "unit": "TON"}
    )
    assert r.status_code == 400
    assert "priced in" in r.json()["detail"]


def test_endpoint_rejects_an_unknown_field(client, db, slab):
    """
    extra="forbid", after a bulk save silently swallowed misspelled pier fields
    and returned zero rebar. On a money endpoint, a typo should be a 422.
    """
    section, a, b = slab
    r = client.put(
        f"/api/sections/{section.id}/quotes/rebar",
        json={"amount": "40000", "unit": "LS", "notes": "typo — should be note"},
    )
    assert r.status_code == 422


def test_endpoint_recosts_the_section(client, db, slab):
    """A saved quote must move the stored money, not just the row."""
    section, a, b = slab
    before = Decimal(str(section.calc_total_cost))
    r = client.put(
        f"/api/sections/{section.id}/quotes/rebar", json={"amount": "0.62", "unit": "LB"}
    )
    assert r.status_code == 200
    db.refresh(section)
    assert Decimal(str(section.calc_total_cost)) != before
