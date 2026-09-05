"""
Every write path, for every assembly: the section is right and the job follows.

Two bugs found by the 2026-09-02 audit, both of the same family — a write path
that does *some* of the work and leaves the rest on pre-edit numbers, with a
200 OK and a plausible total on screen.

  #2  No takeoff endpoint rolled the job up. `refresh_estimate_totals` had five
      callers, all section-level, while every grid save and row edit called
      `refresh_pour_costs` and stopped. One `PUT /api/wall-runs/bulk` moved its
      section from $162,920.41 to $237,719.77 and left the estimate on
      $162,920.41.

  #3  A single-row POST/PATCH/DELETE re-ran the geometry and the cost but not
      the three stored takeoffs. On columns — where supervision derives from the
      column COUNT — PATCHing one type's qty from 38 to 400 left the
      superintendent on 17 days and the section $436,826.42 light.

Both were fixed structurally rather than call-site by call-site, because
call-site-by-call-site is what produced them: eleven sites across five routers
each had to remember, and a twelfth arrives with every new assembly.

  * `costing._roll_up_parent` hangs the roll-up off the six assignments that are
    the ONLY place a section total is written.
  * every router's `_recost` now calls `recalc_section`, the same function
    `/bulk` always called.

This file is written as a MATRIX on purpose. The bug was never in one assembly;
it was in the fact that nobody checked them all the same way. A new assembly
adds one row to ASSEMBLIES here and inherits the whole contract.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.costing import refresh_estimate_totals
from app.services.recalc import recalc_section


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# name, fixture module, rows endpoint, bulk endpoint, a field to bump
ASSEMBLIES = [
    ("walls",   "walls_fixture",     "wall-runs",    "length_ft"),
    ("columns", "columns_fixture",   "column-types", "qty"),
    ("piers",   "piers_fixture",     "pier-groups",  "qty"),
    ("paving",  "paving_fixture",    "mono-slabs",   "square_footage"),
    ("slab",    "mono_slab_fixture", "mono-slabs",   "square_footage"),
    # Absent until 2026-09-04 (audit P2 #9): the deck — the largest section
    # on the job — was in none of the four matrices, against the docstring.
    ("deck",    "deck_fixture",      "deck-levels",  "area_sf"),
]


def _build(db, estimate, mod_name):
    """
    Build a section AND materialise its three takeoffs.

    The materialisation is not decoration. `recalc_section` refreshes forming,
    labor and equipment only `if db.get(EstimateSummary, section.id) is not
    None` — they are built lazily by the first GET. So on a section nobody has
    opened, a PATCH and a full recalc agree trivially, both skipping the same
    work, and a test written against that state passes while the bug is intact.

    The first version of this file did exactly that. It went green before the
    fix was in.
    """
    import importlib

    from app.services.estimate_equipment import get_or_refresh_equipment
    from app.services.forming import get_or_refresh_forming
    from app.services.labor import get_or_refresh_labor

    mod = importlib.import_module(f"tests.{mod_name}")
    section = mod.build(db, estimate)
    if hasattr(mod, "type_the_supervision"):
        mod.type_the_supervision(db, section.id)
    db.flush()
    recalc_section(db, section)
    db.flush()

    # Order matters: equipment reads the superintendent days labor produces.
    get_or_refresh_forming(db, section.id)
    get_or_refresh_labor(db, section.id)
    get_or_refresh_equipment(db, section.id)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _est(db, estimate_id):
    return db.execute(
        text("SELECT calc_total_cost FROM estimates WHERE id = :i"),
        {"i": str(estimate_id)},
    ).scalar()


def _sec(db, section_id):
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _rows(client, endpoint, section_id):
    r = client.get(f"/api/{endpoint}?section_id={section_id}")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("name,mod,endpoint,field", ASSEMBLIES,
                         ids=[a[0] for a in ASSEMBLIES])
def test_a_grid_save_rolls_the_job_up(client, db, estimate, name, mod, endpoint, field):
    """#2, on every assembly. The section moves; the job must move with it."""
    section = _build(db, estimate, mod)
    refresh_estimate_totals(db, estimate)
    db.flush()
    before_s, before_e = _sec(db, section.id), _est(db, estimate.id)

    rows = _rows(client, endpoint, section.id)
    edit = {"id": rows[0]["id"], field: float(rows[0][field]) * 3}
    r = client.put(f"/api/{endpoint}/bulk",
                   json={"section_id": str(section.id), "rows": [edit]})
    assert r.status_code == 200, r.text

    after_s, after_e = _sec(db, section.id), _est(db, estimate.id)
    assert after_s != before_s, f"{name}: the grid save did not move the section"
    assert after_e - before_e == after_s - before_s, (
        f"{name}: section moved {after_s - before_s} and the job moved "
        f"{after_e - before_e} — the roll-up did not follow"
    )


@pytest.mark.parametrize("name,mod,endpoint,field", ASSEMBLIES,
                         ids=[a[0] for a in ASSEMBLIES])
def test_a_single_row_patch_matches_a_full_recalc(
    client, db, estimate, name, mod, endpoint, field
):
    """
    #3, on every assembly, and stated as the property that matters: after a
    PATCH the stored numbers must already be what a full recalc would produce.

    Comparing against `recalc_section` rather than a hardcoded figure is what
    makes this survive a rate change — and it is exactly the comparison that
    was never made, which is how the cheap path stayed wrong.
    """
    section = _build(db, estimate, mod)
    rows = _rows(client, endpoint, section.id)

    r = client.patch(f"/api/{endpoint}/{rows[0]['id']}",
                     json={field: float(rows[0][field]) * 3})
    assert r.status_code == 200, r.text
    after_patch = _sec(db, section.id)

    recalc_section(db, section)
    db.flush()
    after_recalc = _sec(db, section.id)

    assert after_patch == after_recalc, (
        f"{name}: PATCH left the section at {after_patch} where a full recalc "
        f"gives {after_recalc} — {after_recalc - after_patch} of takeoff was "
        f"never re-run"
    )


def test_the_column_count_moves_supervision_on_a_single_row_patch(client, db, estimate):
    """
    The specific $436,826.42, kept as its own test.

    Columns is the only assembly whose duration comes from a COUNT, so it is the
    one where a stale takeoff is a stale superintendent, a stale foreman and a
    stale rental ladder. `routers/column_types.py`'s module docstring promised
    every write path re-runs the section; the PATCH path did not.
    """
    section = _build(db, estimate, "columns_fixture")
    days = lambda: db.execute(
        text("SELECT qty FROM estimate_labor_lines "
             "WHERE section_id = :s AND code ILIKE '%super%'"),
        {"s": str(section.id)},
    ).scalar()
    before = days()
    assert before == Decimal("17.0000"), before

    rows = _rows(client, "column-types", section.id)
    c1 = next(r for r in rows if r["label"] == "C1")     # 38 of the 68
    client.patch(f"/api/column-types/{c1['id']}", json={"qty": 400})

    # 400 + 23 + 1 + 6 = 430 columns; 430 / 20 a week = 21.5 weeks; × 5 = 107.5.
    # The figure the audit measured the $436,826.42 against.
    assert days() == Decimal("107.5000"), (
        f"430 columns must be 107.5 superintendent days, not {days()} — "
        "supervision is derived from the count, and the PATCH left it stale"
    )


@pytest.mark.parametrize("name,mod,endpoint,field", ASSEMBLIES,
                         ids=[a[0] for a in ASSEMBLIES])
def test_a_row_delete_rolls_the_job_up(client, db, estimate, name, mod, endpoint, field):
    """The same hole in the other direction — a removed row still counted."""
    section = _build(db, estimate, mod)
    refresh_estimate_totals(db, estimate)
    db.flush()
    rows = _rows(client, endpoint, section.id)
    if len(rows) < 2:
        pytest.skip("needs two rows to delete one")
    before_s, before_e = _sec(db, section.id), _est(db, estimate.id)

    assert client.delete(f"/api/{endpoint}/{rows[0]['id']}").status_code == 204
    after_s, after_e = _sec(db, section.id), _est(db, estimate.id)

    assert after_s < before_s, f"{name}: deleting a row did not move the section"
    assert after_e - before_e == after_s - before_s, (
        f"{name}: the job did not follow the delete"
    )


def test_the_job_equals_the_sum_of_its_sections_after_every_kind_is_touched(
    client, db, estimate
):
    """
    The invariant itself, on a job carrying all five assemblies at once.

    Every earlier test watches one section move. This one builds the whole job,
    edits one row in each assembly, and then checks the only thing a user ever
    sees: the number at the top equals the numbers underneath it.
    """
    sections = {}
    for name, mod, endpoint, field in ASSEMBLIES:
        sections[name] = (_build(db, estimate, mod), endpoint, field)
    refresh_estimate_totals(db, estimate)
    db.flush()

    for name, (section, endpoint, field) in sections.items():
        rows = _rows(client, endpoint, section.id)
        client.patch(f"/api/{endpoint}/{rows[0]['id']}",
                     json={field: float(rows[0][field]) * 2})

    total = db.execute(
        text("SELECT coalesce(sum(calc_total_cost), 0) FROM estimate_sections "
             "WHERE estimate_id = :e"),
        {"e": str(estimate.id)},
    ).scalar()
    assert _est(db, estimate.id) == total, (
        f"job reads {_est(db, estimate.id)} against {total} of sections"
    )
