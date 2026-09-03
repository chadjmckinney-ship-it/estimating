"""
Quote against catalog — the check that fires on entry, not on the next edit.

## Two different alarms, and the gap between them

`test_quote_staleness.py` covers the first: a lump priced against one takeoff,
sitting over a bigger one. It fires when the TAKEOFF moves.

Nothing fired when the QUOTE was wrong the moment it was typed. On 2026-09-01 a
rebar quote entered as `$0.65 LS` — sixty-five cents, lump, against 21,945 lb —
understated the mono slab by $14,252.58. The catalog said $14,263 for that same
steel, and the app never put the two numbers side by side. It was found because
Chad happened to be looking for how much steel was in the job.

Drilling had this comparison from the day piers were built
(`piers.rate_table_drill_cost`) and it is why a bad drilling number was always
visible on its own terms. This file is that guarantee extended to rebar and PT.

## What is NOT asserted

That anything is refused. A hard validation was offered on 2026-09-01 and
declined — *"Skip it"* — and that was the right call: a sub's real price is
sometimes a third of catalog, and an estimator who cannot enter what he was
quoted will keep the number somewhere the app cannot see. So the comparison is
always shown and only the badge is conditional.

The band is deliberately loose (0.25x–4x, Chad 2026-09-02): decimal-point and
unit mistakes, nothing else. A badge that fires on every good buy is a badge
people learn to ignore, and an ignored badge is worse than none because it looks
like cover.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.services.quotes as qt
from app.db import get_db
from app.main import app
from app.services.costing import catalog_cost_for_quote
from app.services.recalc import recalc_section


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate, mod_name):
    import importlib

    mod = importlib.import_module(f"tests.{mod_name}")
    section = mod.build(db, estimate)
    if hasattr(mod, "type_the_supervision"):
        mod.type_the_supervision(db, section.id)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _q(client, section_id, kind="rebar"):
    body = client.get(f"/api/sections/{section_id}").json()
    return next((x for x in (body.get("quotes") or []) if x["kind"] == kind), None)


def _put(client, section_id, amount, unit, kind="rebar"):
    r = client.put(f"/api/sections/{section_id}/quotes/{kind}",
                   json={"amount": amount, "unit": unit})
    assert r.status_code == 200, r.text
    return r


STEEL_ASSEMBLIES = [
    ("slab",    "mono_slab_fixture"),
    ("paving",  "paving_fixture"),
    ("piers",   "piers_fixture"),
    ("walls",   "walls_fixture"),
    ("columns", "columns_fixture"),
]


# ------------------------------------------------------------- the alarm ----


@pytest.mark.parametrize("name,mod", STEEL_ASSEMBLIES, ids=[a[0] for a in STEEL_ASSEMBLIES])
def test_the_sixty_five_cent_lump_is_flagged_on_entry(client, db, estimate, name, mod):
    """
    The one that started it. Every assembly, on entry — no takeoff edit needed.
    """
    section = _build(db, estimate, mod)
    _put(client, section.id, 0.65, "LS")

    q = _q(client, section.id)
    assert q["catalog_verdict"] == "far_below", (
        f"{name}: $0.65 for the whole steel package read as {q['catalog_verdict']}"
    )
    assert Decimal(str(q["catalog_total"])) > 0
    assert Decimal(str(q["catalog_ratio"])) < Decimal("0.001")
    # And it says so while the staleness badge is still green, which is the
    # entire point — on 2026-09-01 that badge was the only thing watching.
    assert q["stale"] is False


@pytest.mark.parametrize("name,mod", STEEL_ASSEMBLIES, ids=[a[0] for a in STEEL_ASSEMBLIES])
def test_a_sensible_lump_does_not_warn(client, db, estimate, name, mod):
    """
    The other half, and the one that decides whether anybody keeps reading the
    badges: a quote at the catalog's own number must be silent.
    """
    section = _build(db, estimate, mod)
    catalog = catalog_cost_for_quote(db, section, qt.REBAR)
    assert catalog and catalog > 0, f"{name}: no catalog figure to compare against"

    _put(client, section.id, float(catalog), "LS")
    q = _q(client, section.id)
    assert q["catalog_verdict"] == "ok"
    assert Decimal(str(q["catalog_ratio"])) == Decimal("1.0000")


@pytest.mark.parametrize("name,mod", STEEL_ASSEMBLIES, ids=[a[0] for a in STEEL_ASSEMBLIES])
def test_a_real_bargain_stays_quiet(client, db, estimate, name, mod):
    """
    A sub at 40% under catalog is a good day, not an error. This is the case
    the loose band exists for — and the reason a tighter one was rejected.
    """
    section = _build(db, estimate, mod)
    catalog = catalog_cost_for_quote(db, section, qt.REBAR)
    _put(client, section.id, float(catalog) * 0.6, "LS")
    assert _q(client, section.id)["catalog_verdict"] == "ok"


@pytest.mark.parametrize("name,mod", STEEL_ASSEMBLIES, ids=[a[0] for a in STEEL_ASSEMBLIES])
def test_a_rate_typed_where_a_lump_belongs_is_flagged(client, db, estimate, name, mod):
    """The mirror mistake: $0.65/lb entered as a lump of $0.65 is far_below;
    a lump of $14,263 entered as a RATE is far_above by roughly the tonnage."""
    section = _build(db, estimate, mod)
    catalog = catalog_cost_for_quote(db, section, qt.REBAR)
    _put(client, section.id, float(catalog), "LB")     # dollars-per-pound, wildly
    q = _q(client, section.id)
    assert q["catalog_verdict"] == "far_above", q


# ------------------------------------------- unit prices are checked too ----


@pytest.mark.parametrize("name,mod", STEEL_ASSEMBLIES, ids=[a[0] for a in STEEL_ASSEMBLIES])
def test_a_unit_price_is_compared_on_its_extended_total(client, db, estimate, name, mod):
    """
    "All quotes" means unit-priced ones too. `$6.50/LB` instead of `$0.65/LB` is
    the same decimal-point slip as a mistyped lump, and a unit price cannot go
    stale — so without this it has no check at all.
    """
    section = _build(db, estimate, mod)
    steel = qt.section_driver_qty(db, section, qt.REBAR)

    _put(client, section.id, 0.65, "LB")
    ok = _q(client, section.id)
    assert ok["catalog_verdict"] == "ok"
    assert Decimal(str(ok["quoted_total"])) == (
        Decimal("0.65") * steel
    ).quantize(Decimal("0.01"))

    _put(client, section.id, 6.50, "LB")               # the slipped decimal
    assert _q(client, section.id)["catalog_verdict"] == "far_above"


def test_ton_and_cwt_are_extended_before_comparing(client, db, estimate):
    """
    A fabricator quotes $/cwt; the comparison must convert before judging, or
    every cwt quote reads as 100x low and the badge becomes noise.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    steel = qt.section_driver_qty(db, section, qt.REBAR)

    for amount, unit, per_lb in ((1300, "TON", Decimal("0.65")),
                                 (65, "CWT", Decimal("0.65"))):
        _put(client, section.id, amount, unit)
        q = _q(client, section.id)
        assert q["catalog_verdict"] == "ok", f"{amount} {unit} -> {q}"
        assert Decimal(str(q["quoted_total"])) == (per_lb * steel).quantize(
            Decimal("0.01")
        ), f"{unit} was not extended to a total"


# --------------------------------------------------- honest about unknowns ----


def test_no_catalog_price_gives_no_verdict_rather_than_ok(client, db, estimate):
    """
    "We could not check this" and "we checked this and it is fine" are different
    states, and a card that shows them the same way is lying about its coverage.

    Same rule as `rate_table_drill_cost`, which returns None rather than a
    partial total — a partial invites subtracting it from the quote and calling
    the difference a saving.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    # The estimate prices from its SHEET (sql/048), so a price has to be
    # absent from the sheet, not merely from the catalog — NULLing the catalog
    # alone changes nothing on a priced job, which is the feature. This test
    # used to NULL `materials.unit_cost` and went red the day the sheet landed:
    # the comparison still had the pulled price and quite rightly used it.
    db.execute(
        text("DELETE FROM estimate_prices WHERE estimate_id = :e AND kind = 'material' "
             "AND label ILIKE '%REBAR%'"),
        {"e": str(estimate.id)},
    )
    db.flush()

    _put(client, section.id, 20000, "LS")
    q = _q(client, section.id)
    assert q["catalog_total"] is None
    assert q["catalog_verdict"] is None, (
        "an unpriced catalog must produce no verdict, not a passing one"
    )


def test_drilling_keeps_the_comparison_it_always_had(client, db, estimate):
    """Piers' rate table is the catalog figure for drilling — unchanged."""
    section = _build(db, estimate, "piers_fixture")
    table = catalog_cost_for_quote(db, section, qt.DRILLING)
    assert table and table > 0

    _put(client, section.id, 1.00, "LS", kind="drilling")
    q = _q(client, section.id, "drilling")
    assert q["catalog_verdict"] == "far_below"
    assert Decimal(str(q["catalog_total"])) == table


# ------------------------------------------------------------ the band ----


def test_the_band_is_configurable_per_assembly(client, db, estimate):
    """
    A ratio is a rule, not a price, so it lives in settings — and an assembly
    can hold its own. Sized loose on purpose; this is how it gets tightened for
    one kind of work without touching the rest.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    catalog = catalog_cost_for_quote(db, section, qt.REBAR)
    _put(client, section.id, float(catalog) * 0.6, "LS")
    assert _q(client, section.id)["catalog_verdict"] == "ok"

    db.execute(
        text("INSERT INTO assembly_rates (kind, key, value, note) "
             "VALUES ('mono_slab', 'quote_warn_low_ratio', '0.75', 'tightened') "
             "ON CONFLICT (kind, key) DO UPDATE SET value = excluded.value"),
    )
    db.flush()
    assert _q(client, section.id)["catalog_verdict"] == "far_below"


def test_the_default_band_is_the_one_that_was_chosen(db):
    """0.25x-4x. Written down so a later 'tidy-up' has to argue with it."""
    assert qt.WARN_LOW_RATIO == Decimal("0.25")
    assert qt.WARN_HIGH_RATIO == Decimal("4")
    rows = dict(
        db.execute(
            text("SELECT key, value #>> '{}' FROM system_settings "
                 "WHERE key LIKE 'quote_warn%'")
        ).all()
    )
    assert Decimal(rows["quote_warn_low_ratio"]) == Decimal("0.25")
    assert Decimal(rows["quote_warn_high_ratio"]) == Decimal("4")
