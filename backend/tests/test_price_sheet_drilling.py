"""
The estimate price sheet (sql/050) — stage 4: drilling rates by shaft diameter.

The last table-held price that was still read live. `pier_drill_rates` is
~20% of a piers section and it is the number a driller's quote is judged
against, so both the cost and the comparison have to come off this job's
sheet.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.estimate import Estimate
from app.models.estimate_price import EstimatePrice
from app.models.pier_group import PierGroup
from app.services import piers as pv
from app.services import price_book as pb
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.piers import section_pier_totals
from app.services.recalc import recalc_section
from tests import piers_fixture as pf


def _build(db, estimate):
    section = pf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    pf.type_the_supervision(db, section.id)      # last, as test_piers does
    refresh_pour_costs(db, section)
    db.flush()
    # Typing the supervision moves the equipment ladder on the NEXT refresh
    # (audit #5), so settle the section once here — every before/after below
    # is then a drilling difference and nothing else.
    recalc_section(db, section)
    db.flush()
    return section


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _groups(db, sid) -> list[PierGroup]:
    return list(db.scalars(select(PierGroup).where(PierGroup.section_id == sid)
                           .order_by(PierGroup.sort_order)).all())


def _drill_row(db, estimate_id, diameter) -> EstimatePrice | None:
    return db.scalars(select(EstimatePrice).where(
        EstimatePrice.estimate_id == estimate_id,
        EstimatePrice.kind == "drill_rate",
        EstimatePrice.ref_key == pb.drill_key(diameter),
    )).first()


def test_the_pull_carries_every_priced_diameter(db, estimate):
    _build(db, estimate)
    table = {pb.drill_key(r[0]): Decimal(str(r[1])) for r in
             db.execute(text("SELECT diameter_in, drill_per_lf FROM pier_drill_rates WHERE drill_per_lf > 0"))}
    sheet = {p.ref_key: Decimal(str(p.value)) for p in pb.sheet_rows(db, estimate.id) if p.kind == "drill_rate"}
    assert sheet == table and table, "every diameter on the table, at the table's rate"
    assert pb.drill_key(Decimal("24.00")) == "24" == pb.drill_key(24)


def test_a_sheeted_piers_section_drills_at_the_golden_total(db, estimate):
    section = _build(db, estimate)
    t = section_pier_totals(db, section.id)
    assert Decimal(str(t["total_drill_cost"])) == pf.SHEET["drilling"]
    assert t["groups_without_drill_rate"] == 0
    assert _cost(db, section.id) > 0


def test_a_drillers_break_on_this_job_reaches_this_job_only(db, project):
    a = Estimate(project_id=project.id, name="A"); db.add(a); db.flush()
    b = Estimate(project_id=project.id, name="B"); db.add(b); db.flush()
    sa = _build(db, a)
    sb = _build(db, b)
    cost_b0 = _cost(db, sb.id)
    assert _cost(db, sa.id) == cost_b0

    ga = _groups(db, sa.id)
    dia = ga[0].diameter_in
    lf_at_dia = sum(_d(g.calc_total_lf) for g in ga if g.diameter_in == dia)
    row = _drill_row(db, a.id, dia)
    assert row is not None
    was = Decimal(str(row.value))
    pb.set_price(db, row, value=was - Decimal("2"), note="driller has the rig on site")
    recalc_section(db, sa); db.flush()

    drop = _cost(db, sb.id) - _cost(db, sa.id)
    expected = (Decimal("2") * lf_at_dia)
    assert abs(drop - expected) <= Decimal("0.05"), (drop, expected)
    assert _cost(db, sb.id) == cost_b0, "the other job did not move"


def test_a_table_change_does_not_move_a_priced_section_but_is_reported(db, estimate):
    section = _build(db, estimate)
    before = _cost(db, section.id)
    db.execute(text("UPDATE pier_drill_rates SET drill_per_lf = drill_per_lf + 5"))
    db.flush()
    recalc_section(db, section); db.flush()
    assert _cost(db, section.id) == before
    d = pb.drift(db, estimate.id)
    assert {c["ref_key"] for c in d.changed if c["kind"] == "drill_rate"} == {
        p.ref_key for p in pb.sheet_rows(db, estimate.id) if p.kind == "drill_rate"
    }


def test_the_quote_comparison_is_at_this_jobs_rates(db, estimate):
    """`drill_rate_cost` beside a quote is "what would we have charged" — at the
    sheet's rates, or a negotiated table on one job makes every quote read off."""
    from tests.test_pier_drill_quote import QUOTE, RATE_TABLE_DRILLING, set_quote

    section = _build(db, estimate)
    set_quote(db, section, QUOTE)
    assert Decimal(str(section_pier_totals(db, section.id)["drill_rate_cost"])) == RATE_TABLE_DRILLING

    for p in pb.sheet_rows(db, estimate.id):
        if p.kind == "drill_rate":
            pb.set_price(db, p, value=Decimal(str(p.value)) * 2)
    recalc_section(db, section); db.flush()
    t = section_pier_totals(db, section.id)
    assert Decimal(str(t["drill_rate_cost"])) == RATE_TABLE_DRILLING * 2
    assert t["drill_quote_basis"] == "rate_shape"


def test_a_diameter_off_the_sheet_is_unpriced_not_interpolated(db, estimate):
    """The rule the table always had — no row, no guess — now applied to the
    sheet: a diameter whose row was never pulled prices at nothing and says so."""
    section = _build(db, estimate)
    g = _groups(db, section.id)[0]
    db.delete(_drill_row(db, estimate.id, g.diameter_in)); db.flush()
    pv.refresh_pier_group_calcs(db, g, section); db.flush()
    assert g.calc_drill_lf_rate is None and g.calc_drill_cost is None
    assert section_pier_totals(db, section.id)["groups_without_drill_rate"] >= 1
    assert any(n["kind"] == "drill_rate" and n["ref_key"] == pb.drill_key(g.diameter_in)
               for n in pb.drift(db, estimate.id).new)


def test_a_zero_or_null_table_rate_is_unpriced(db, project):
    fresh = Estimate(project_id=project.id, name="fresh"); db.add(fresh); db.flush()
    db.execute(text("UPDATE pier_drill_rates SET drill_per_lf = 0 WHERE diameter_in = 16"))
    db.flush()
    result = pb.pull_prices(db, fresh.id)
    assert any(u["kind"] == "drill_rate" and u["ref_key"] == "16" for u in result.unpriced)
    assert _drill_row(db, fresh.id, 16) is None
    row = _drill_row(db, fresh.id, 18)
    with pytest.raises(ValueError):
        pb.set_price(db, row, value=Decimal("0"))


def test_the_guard_covers_drilling(db):
    with pytest.raises(pb.NoPriceBook):
        pv.drill_rate(db, Decimal("24"))
    with pb.catalog_only():
        assert pv.drill_rate(db, Decimal("24")) == Decimal("8")


def _d(x) -> Decimal:
    return Decimal(str(x)) if x is not None else Decimal("0")
