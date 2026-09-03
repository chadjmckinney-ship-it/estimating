"""
The job total must equal the sum of its sections, on a session that does not
autoflush.

## What happened

On 2026-09-01 the mono slab on estimate 152b3611 read $672,900.43 and the
estimate above it read a total containing $657,460.08 for that same section —
$15,440.35 behind. Nothing was wrong with either number in isolation. The
section had been re-costed and rolled up in one request, and the rollup, which
reads `estimate_sections` in raw SQL, ran before the section's new
`calc_total_cost` had been flushed. It saw the row as it was before the edit.

It only happened in production. `app/db.py` builds its sessions
`autoflush=False`; `conftest.py` used to build the test session at the
SQLAlchemy default of True. Every call site got a free flush under test and
none on the server, so 307 passing tests said the rollup was correct while it
was one edit behind on every write path that touches it. **conftest now matches
production** (2026-09-01), so the whole suite would catch this today.

## Why this file opens its own session

Because the point is the flush, and a session that autoflushes cannot fail this
test no matter how broken `refresh_estimate_totals` is. So it builds a session
shaped like production's — same connection, same rollback, `autoflush=False` —
and drives the rollup the way a request does: mutate through the ORM, then roll
up without flushing in between.

Flipping conftest's session to match production was the real fix and has since
been done. It surfaced the second instance immediately — `_super_days` feeding
a zero-day rental ladder on piers — which is now fixed the same way. This file
stays because it names the bug directly: a suite-wide setting protects against
regression, but nothing else says *why* that setting matters.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.services.costing import refresh_estimate_totals


@pytest.fixture
def prod_db(db):
    """
    A second session on the SAME connection, shaped like app/db.py's.

    Sharing the connection keeps everything inside the outer transaction the
    `db` fixture rolls back, so this writes nothing that survives the test.
    """
    s = Session(
        bind=db.connection(),
        join_transaction_mode="create_savepoint",
        autoflush=False,
    )
    try:
        yield s
    finally:
        s.close()


def _sections(session, estimate_id) -> list[EstimateSection]:
    return list(
        session.scalars(
            select(EstimateSection)
            .where(EstimateSection.estimate_id == estimate_id)
            .order_by(EstimateSection.sort_order)
        ).all()
    )


def test_the_rollup_sees_an_unflushed_section(prod_db, project):
    """
    Write a section total through the ORM, roll up WITHOUT flushing, and the
    job total has to include what was just written.

    Before the fix this returned the pre-edit sum. It is deliberately not
    testing any pricing rule — the arithmetic is trivial on purpose, so a
    failure here means exactly one thing.
    """
    est = Estimate(project_id=project.id, name="rollup", status="draft")
    prod_db.add(est)
    prod_db.flush()

    for i, cost in enumerate((Decimal("100.00"), Decimal("250.00"))):
        prod_db.add(
            EstimateSection(
                estimate_id=est.id,
                kind="mono_slab",
                name=f"S{i}",
                unit="SF",
                sort_order=i,
                calc_total_cost=cost,
                calc_total_sale=cost * 2,
                calc_total_tax=Decimal("0.00"),
            )
        )
    prod_db.flush()

    refresh_estimate_totals(prod_db, est)
    assert est.calc_total_cost == Decimal("350.00")

    # Now the part that used to break: edit through the ORM, do NOT flush.
    section = _sections(prod_db, est.id)[0]
    section.calc_total_cost = Decimal("1100.00")
    section.calc_total_sale = Decimal("2200.00")

    refresh_estimate_totals(prod_db, est)
    assert est.calc_total_cost == Decimal("1350.00"), (
        "the job total rolled up from pre-edit rows — refresh_estimate_totals "
        "reads in raw SQL and must flush first"
    )
    assert est.calc_total_sale == Decimal("2700.00")


def test_a_section_delete_is_visible_to_the_rollup_too(prod_db, project):
    """The same hole in the other direction: a removed section still counted."""
    est = Estimate(project_id=project.id, name="rollup-del", status="draft")
    prod_db.add(est)
    prod_db.flush()

    for i, cost in enumerate((Decimal("400.00"), Decimal("600.00"))):
        prod_db.add(
            EstimateSection(
                estimate_id=est.id, kind="mono_slab", name=f"S{i}", unit="SF",
                sort_order=i, calc_total_cost=cost, calc_total_sale=cost,
                calc_total_tax=Decimal("0.00"),
            )
        )
    prod_db.flush()

    prod_db.delete(_sections(prod_db, est.id)[0])
    refresh_estimate_totals(prod_db, est)
    assert est.calc_total_cost == Decimal("600.00")


def test_recalc_section_flushes_even_when_it_skips_the_pours(prod_db, project):
    """
    `recalc_section(..., pours=False)` must still flush before it rebuilds the
    takeoffs.

    The flush used to live inside `if pours:`, where it looked sufficient — the
    pour recalc is the obvious writer of pending ORM state. But `pours=False`
    exists precisely FOR callers that wrote the geometry themselves and want
    only the takeoffs rebuilt, and those are the callers whose writes are
    pending. Forming, labor and equipment all read their drivers in raw SQL, so
    under `autoflush=False` they saw pre-edit rows.

    Reached in the wild through `routers/grade_beams.py`, the only caller that
    passes `pours=False` — and one that was returning 500 for an unrelated
    reason, so nothing ever exercised it. Adding 500 LF of reinforced grade beam
    moved the pour from 2,447 lb to 5,931 lb of steel and left the stored labor
    summary sitting on 21,944.977.

    This test does not go near a grade beam: it writes a pour's stored steel
    through the ORM, leaves it unflushed, and asserts the labor summary catches
    up. If the flush moves back inside the `if`, this fails.
    """
    from sqlalchemy import text as _text

    from app.services.labor import get_or_refresh_labor
    from app.services.recalc import recalc_section
    from tests import mono_slab_fixture as mf

    est = Estimate(project_id=project.id, name="recalc-flush", status="draft")
    prod_db.add(est)
    prod_db.flush()
    section = mf.build(prod_db, est)
    recalc_section(prod_db, section)
    prod_db.flush()
    get_or_refresh_labor(prod_db, section.id)      # materialise the summary
    prod_db.flush()

    stored = lambda: prod_db.execute(
        _text("SELECT total_rebar_lb FROM estimate_labor_summary WHERE section_id = :s"),
        {"s": str(section.id)},
    ).scalar()
    before = stored()
    assert before and before > 0

    # Write through the ORM and deliberately do NOT flush — exactly the state a
    # caller is in when it hands us pours=False.
    pour = prod_db.scalars(
        _text("SELECT id FROM mono_slabs WHERE section_id = :s ORDER BY created_at LIMIT 1")
        .bindparams(s=str(section.id))
    ).first()
    from app.models.mono_slab import MonoSlab

    slab = prod_db.get(MonoSlab, pour)
    slab.calc_total_rebar_lb = Decimal(str(slab.calc_total_rebar_lb)) + Decimal("5000")

    recalc_section(prod_db, section, pours=False)
    prod_db.flush()

    assert stored() == before + Decimal("5000"), (
        "recalc_section rebuilt the takeoffs from pre-edit rows — it must flush "
        "before the drivers read in raw SQL, pours or no pours"
    )
