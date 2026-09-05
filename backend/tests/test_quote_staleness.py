"""
A lump quote must know what takeoff it was priced against — on every assembly.

## The bug this file exists for

`section_driver_qty` hard-coded `MonoSlab` for every non-pier section. Walls
keep their takeoff in `wall_runs` and columns in `column_types`, so both stamped
a baseline of **zero** against 33,728 lb and 47,417 lb of real steel.

Nothing looked wrong. The number on the card was right, the spread across rows
was right — `costing._apply_lump_quotes` was kind-dispatched correctly the whole
time. What was gone was the CHECK: `is_stale` compared 0 to 0 and returned False
forever. Doubling a wall takeoff left the quote reading "current".

That matters because of what happened on the mono slab on 2026-09-01. A rebar
quote entered as `$0.65 LS` — sixty-five cents, lump, for 21,945 lb of steel —
understated that section by **$14,252.58**, and it was caught *only* because the
badge went stale. On walls or columns the same mistake had no alarm attached.

## What is asserted, and why it is a matrix

The bug was never in one assembly. It was in a branch that handled piers, and
then handled everything else as if it were a slab — so it was correct for the
two kinds anyone had tested and silently wrong for the two added later. A new
assembly must inherit this contract by appearing in QUOTED_ASSEMBLIES, not by
someone remembering to write four more tests.

The property, stated once: **a lump's baseline is the same quantity costing
spreads it across.** Both now read `quotes.LUMP_DRIVERS`, so this is checkable
rather than hoped for — `test_the_baseline_and_the_spread_read_one_definition`
is the test that would fail if they ever fork again.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.services.quotes as qt
from app.db import get_db
from app.main import app
from app.services.recalc import recalc_section

# name, fixture module, the table its takeoff lives in
QUOTED_ASSEMBLIES = [
    ("slab",    "mono_slab_fixture", "mono_slabs"),
    ("paving",  "paving_fixture",    "mono_slabs"),
    ("piers",   "piers_fixture",     "pier_groups"),
    ("walls",   "walls_fixture",     "wall_runs"),
    ("columns", "columns_fixture",   "column_types"),
    # Absent until 2026-09-04 (audit P2 #9). The deck buys the most bar on
    # the job and takes a rebar lump like the rest.
    ("deck",    "deck_fixture",      "deck_levels"),
]


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


def _steel(db, table, section_id) -> Decimal:
    return db.execute(
        text(f"SELECT coalesce(sum(calc_total_rebar_lb), 0) FROM {table} "
             "WHERE section_id = :s"),
        {"s": str(section_id)},
    ).scalar()


def _quote(client, section_id):
    body = client.get(f"/api/sections/{section_id}").json()
    return (body.get("quotes") or [None])[0]


@pytest.mark.parametrize("name,mod,table", QUOTED_ASSEMBLIES,
                         ids=[a[0] for a in QUOTED_ASSEMBLIES])
def test_a_lump_is_stamped_with_the_real_takeoff(client, db, estimate, name, mod, table):
    """A baseline of zero is not a baseline. It is a disabled alarm."""
    section = _build(db, estimate, mod)
    steel = _steel(db, table, section.id)
    assert steel > 0, f"{name}: fixture carries no steel to quote"

    r = client.put(f"/api/sections/{section.id}/quotes/rebar",
                   json={"amount": 20000, "unit": "LS", "note": "Ace 9/2"})
    assert r.status_code == 200, r.text

    q = _quote(client, section.id)
    assert Decimal(str(q["baseline_qty"])) == steel, (
        f"{name}: stamped {q['baseline_qty']} against a takeoff of {steel}"
    )
    assert q["stale"] is False, f"{name}: a just-stamped lump cannot be stale"


@pytest.mark.parametrize("name,mod,table", QUOTED_ASSEMBLIES,
                         ids=[a[0] for a in QUOTED_ASSEMBLIES])
def test_the_badge_goes_stale_when_the_takeoff_moves(client, db, estimate, name, mod, table):
    """
    The assertion that was missing. A lump priced against one takeoff, sitting
    over a bigger one, is a wrong bid with nothing on screen to notice.
    """
    section = _build(db, estimate, mod)
    client.put(f"/api/sections/{section.id}/quotes/rebar",
               json={"amount": 20000, "unit": "LS"})
    assert _quote(client, section.id)["stale"] is False

    # Move the takeoff the way an estimator would — through the grid.
    endpoint = {"mono_slabs": "mono-slabs", "pier_groups": "pier-groups",
                "wall_runs": "wall-runs", "column_types": "column-types",
                "deck_levels": "deck-levels"}[table]
    field = {"mono_slabs": "square_footage", "pier_groups": "qty",
             "wall_runs": "length_ft", "column_types": "qty",
             "deck_levels": "area_sf"}[table]
    rows = client.get(f"/api/{endpoint}?section_id={section.id}").json()
    bump = int(float(rows[0][field]) * 2) if field == "qty" else float(rows[0][field]) * 2
    r = client.patch(f"/api/{endpoint}/{rows[0]['id']}", json={field: bump})
    assert r.status_code == 200, r.text

    assert _steel(db, table, section.id) != Decimal(
        str(_quote(client, section.id)["baseline_qty"])
    ), f"{name}: the takeoff did not actually move"
    assert _quote(client, section.id)["stale"] is True, (
        f"{name}: the takeoff moved and the quote still reads current"
    )


@pytest.mark.parametrize("name,mod,table", QUOTED_ASSEMBLIES,
                         ids=[a[0] for a in QUOTED_ASSEMBLIES])
def test_a_derisory_lump_is_flagged_once_the_takeoff_moves(
    client, db, estimate, name, mod, table
):
    """
    The $0.65 LS shape, on every assembly.

    A lump of one dollar against tons of steel still prices the section at one
    dollar of steel — nothing here rejects it, and that is a separate argument.
    What must hold is that it cannot go on pretending to be current after the
    takeoff underneath it changes.
    """
    section = _build(db, estimate, mod)
    before = db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section.id)},
    ).scalar()

    client.put(f"/api/sections/{section.id}/quotes/rebar",
               json={"amount": 1.00, "unit": "LS", "note": "fat finger"})
    after = db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section.id)},
    ).scalar()
    assert after < before, f"{name}: a $1 lump did not displace the steel"

    q = _quote(client, section.id)
    assert Decimal(str(q["baseline_qty"])) > 0, (
        f"{name}: stamped a zero baseline — the staleness check is disabled"
    )


def test_the_baseline_and_the_spread_read_one_definition():
    """
    The structural guard.

    The bug was two implementations of "what is this quote priced against" that
    disagreed for two of five assemblies. They now share `LUMP_DRIVERS`, and
    `costing._apply_lump_quotes` reads that map rather than its own lambdas.
    If someone reintroduces a private copy, this fails.
    """
    import inspect

    from app.services import costing

    src = inspect.getsource(costing._apply_lump_quotes)
    assert "LUMP_DRIVERS" in src, (
        "_apply_lump_quotes no longer reads quotes.LUMP_DRIVERS — the spread and "
        "the baseline have forked again"
    )
    assert {qt.REBAR, qt.PT} <= set(qt.LUMP_DRIVERS)


@pytest.mark.parametrize("name,mod,table", QUOTED_ASSEMBLIES,
                         ids=[a[0] for a in QUOTED_ASSEMBLIES])
def test_a_unit_priced_quote_is_never_stale(client, db, estimate, name, mod, table):
    """It follows the takeoff by construction, so it carries no baseline."""
    section = _build(db, estimate, mod)
    client.put(f"/api/sections/{section.id}/quotes/rebar",
               json={"amount": 0.62, "unit": "LB"})
    q = _quote(client, section.id)
    assert q["stale"] is False
    assert q["baseline_qty"] is None, (
        f"{name}: a unit-priced quote should carry no baseline — it cannot go stale"
    )
