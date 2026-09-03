"""
The estimate price sheet (sql/048) — stage 1: mixes and materials.

claude/estimate-price-sheet-spec.md. Each test below is one line of that spec's
"New tests needed" list, in order, plus the API.

The one that matters most is the first: a pull reproduces the master list
EXACTLY, so the migration's backfill moves no number. Every fixture in this
suite now pulls a sheet before it builds (see the note in each `build()`), so
all ~450 golden tests already run through the book — this file is where the
sheet's own behaviour is pinned.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db import get_db
from app.main import app
from app.models.estimate import Estimate
from app.models.estimate_price import EstimatePrice
from app.services import price_book as pb
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.recalc import recalc_estimate, recalc_section


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
    return _store(db, section)


def _store(db, section):
    """Store every takeoff, the way opening the estimate does. `recalc_section`
    only refreshes what is already stored, so the golden total needs this once."""
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _row(db, estimate_id, kind, ref_id) -> EstimatePrice | None:
    return db.scalars(
        select(EstimatePrice).where(
            EstimatePrice.estimate_id == estimate_id,
            EstimatePrice.kind == kind,
            EstimatePrice.ref_id == ref_id,
        )
    ).first()


def _price_mix(db, mix_id: int, cost: str) -> None:
    """The test catalog ships every mix unpriced; a fixture prices only its own.
    A test that needs a second priced mix says so here."""
    db.execute(text("UPDATE mix_designs SET unit_cost = :c WHERE id = :i"), {"c": cost, "i": mix_id})
    db.flush()


def _mix_on(db, section_id) -> int:
    return db.execute(
        text("SELECT mix_design_id FROM mono_slabs WHERE section_id = :s LIMIT 1"),
        {"s": str(section_id)},
    ).scalar()


# ----------------------------------------------------------- the pull ----


def test_a_pull_reproduces_the_master_list_exactly(db, estimate):
    """The migration's zero-change proof, as a unit: every priced mix and
    material lands on the sheet at the master's own number, and nothing else."""
    result = pb.pull_prices(db, estimate.id)
    assert result.applied
    assert result.new, "a fresh estimate should pull the whole list"

    master = {}
    for r in db.execute(text("SELECT id, unit_cost FROM mix_designs WHERE is_active AND unit_cost IS NOT NULL")):
        master[("mix", "", r[0])] = Decimal(str(r[1]))
    for r in db.execute(text("SELECT id, unit_cost FROM materials WHERE coalesce(is_active,true) AND unit_cost IS NOT NULL")):
        master[("material", "", r[0])] = Decimal(str(r[1]))
    # stage 2 (sql/049): equipment, and the monetary keys of both rate tables
    for r in db.execute(text("SELECT id, unit_cost FROM equipment WHERE is_active AND unit_cost > 0")):
        master[("equipment", "", r[0])] = Decimal(str(r[1]))
    for r in db.execute(text("SELECT key, value #>> '{}' FROM system_settings")):
        if r[0] in pb.MONETARY_KEYS:
            master[("setting", "", r[0])] = Decimal(str(r[1]))
    for r in db.execute(text("SELECT kind, key, value FROM assembly_rates")):
        if r[1] in pb.MONETARY_KEYS:
            master[("assembly_rate", r[0], r[1])] = Decimal(str(r[2]))
    # stage 4 (sql/050): drilling by diameter
    for r in db.execute(text("SELECT diameter_in, drill_per_lf FROM pier_drill_rates WHERE drill_per_lf > 0")):
        master[("drill_rate", "", pb.drill_key(r[0]))] = Decimal(str(r[1]))

    sheet = {
        (p.kind, p.scope or "", p.ref_key or p.ref_id): Decimal(str(p.value))
        for p in pb.sheet_rows(db, estimate.id)
    }
    assert sheet == master
    assert any(k[0] == "equipment" for k in sheet) and any(k[0] == "setting" for k in sheet)
    assert any(k[0] == "assembly_rate" for k in sheet)
    assert all(not p.is_edited for p in pb.sheet_rows(db, estimate.id))


def test_a_sheeted_section_costs_exactly_what_a_catalog_section_did(db, project):
    """
    The same fixture, once with a sheet and once without, must cost the same.
    This is the assertion that every golden test already makes implicitly; it
    is stated here on its own so a future change to the book fails HERE with a
    name, not in `test_mono_slab_golden` with a number.
    """
    from tests import mono_slab_fixture as mf

    with_sheet = Estimate(project_id=project.id, name="sheeted"); db.add(with_sheet); db.flush()
    s1 = _store(db, mf.build(db, with_sheet))     # build() pulls
    assert pb.load_price_book(db, with_sheet.id).has_sheet

    without = Estimate(project_id=project.id, name="catalog"); db.add(without); db.flush()
    s2 = _store(db, mf.build_section(db, without, mf.price_the_catalog(db)))   # no pull
    assert not pb.load_price_book(db, without.id).has_sheet

    assert _cost(db, s1.id) == _cost(db, s2.id) == mf.GOLDEN_COST["total_cost"]


def test_a_pull_never_writes_a_zero_from_an_unpriced_master_item(db, estimate):
    """Decision 5. An unpriced master item is REPORTED, and its row is absent."""
    db.execute(text("UPDATE mix_designs SET unit_cost = NULL WHERE id = 3"))
    db.flush()
    result = pb.pull_prices(db, estimate.id)
    assert any(u["kind"] == "mix" and u["ref_id"] == 3 for u in result.unpriced)
    assert _row(db, estimate.id, "mix", 3) is None
    # A zero RATE is a statement (paving pumps nothing) and is copied; a zero
    # mix, material or machine never is.
    assert not any(
        p.value == 0 for p in pb.sheet_rows(db, estimate.id)
        if p.kind in ("mix", "material", "equipment")
    )


# ------------------------------------------------------ edit and freeze ----


def test_an_edited_price_reaches_the_bid_and_only_this_jobs_bid(db, project):
    """
    "on this job, concrete is $168." The plant's break lands on this estimate
    and on no other — which is what the catalog could never do.
    """
    from tests import mono_slab_fixture as mf

    a = Estimate(project_id=project.id, name="A"); db.add(a); db.flush()
    b = Estimate(project_id=project.id, name="B"); db.add(b); db.flush()
    sa = _store(db, mf.build(db, a))
    sb = _store(db, mf.build(db, b))
    assert _cost(db, sa.id) == _cost(db, sb.id)

    mix_id = _mix_on(db, sa.id)
    row = _row(db, a.id, "mix", mix_id)
    before_rate = Decimal(str(row.value))
    pb.set_price(db, row, value=before_rate - Decimal("10"), note="plant break, 2,205 CY")
    recalc_estimate(db, a); db.flush()

    cy = db.execute(text("SELECT sum(calc_concrete_cy) FROM mono_slabs WHERE section_id = :s"),
                    {"s": str(sa.id)}).scalar()
    # $10/CY less, taxed at 8.25%. Pour costs are quantized per pour and the
    # fixture has 17 of them, so the drop may differ from the one-line
    # arithmetic by up to a cent a pour.
    expected_drop = Decimal(str(cy)) * Decimal("10") * Decimal("1.0825")
    assert abs((_cost(db, sb.id) - _cost(db, sa.id)) - expected_drop) <= Decimal("0.17")
    assert row.is_edited and row.note == "plant break, 2,205 CY"


def test_a_master_list_change_does_not_move_a_priced_estimate(db, estimate):
    """
    The −$4,984.91 morning, prevented. Two equipment rates moved in the
    catalog on 2026-08-31 and a live section moved with them. With a sheet,
    the catalog is free to move and the bid stays where it was bid.
    """
    from tests import mono_slab_fixture as mf

    section = _build(db, estimate, "mono_slab_fixture")
    before = _cost(db, section.id)

    db.execute(text("UPDATE mix_designs SET unit_cost = unit_cost + 25"))
    db.execute(text("UPDATE materials SET unit_cost = unit_cost * 2 WHERE unit_cost IS NOT NULL"))
    db.flush()
    recalc_section(db, section); db.flush()

    assert _cost(db, section.id) == before == mf.GOLDEN_COST["total_cost"]


def test_a_master_list_change_is_reported_as_drift(db, estimate):
    """...and the estimate can say exactly what moved, without applying it."""
    _build(db, estimate, "mono_slab_fixture")
    assert pb.drift(db, estimate.id).drift == 0

    db.execute(text("UPDATE mix_designs SET unit_cost = unit_cost + 25 WHERE id = 3"))
    db.flush()
    d = pb.drift(db, estimate.id)
    assert d.drift == 1
    assert not d.applied
    ch = d.changed[0]
    assert ch["kind"] == "mix" and ch["ref_id"] == 3
    assert Decimal(ch["now"]) - Decimal(ch["was"]) == Decimal("25")
    assert Decimal(ch["yours"]) == Decimal(ch["was"]), "a dry run must not apply"


def test_a_repull_follows_unedited_rows_and_never_overwrites_edited_ones(db, estimate):
    """The rule that makes editing safe. Yours is kept; the master value beside
    it is refreshed so the screen can show was / now / yours."""
    _price_mix(db, 2, "140")                      # a second priced mix to follow
    _build(db, estimate, "mono_slab_fixture")
    edited = _row(db, estimate.id, "mix", 3)
    untouched = _row(db, estimate.id, "mix", 2)
    master_of_3 = Decimal(str(edited.catalog_value))
    pb.set_price(db, edited, value=Decimal("111"))

    db.execute(text("UPDATE mix_designs SET unit_cost = unit_cost + 25 WHERE id IN (2, 3)"))
    db.flush()
    result = pb.pull_prices(db, estimate.id)

    assert len(result.changed) == 1 and result.changed[0]["ref_id"] == 2
    assert len(result.conflicts) == 1 and result.conflicts[0]["ref_id"] == 3

    db.refresh(edited); db.refresh(untouched)
    assert Decimal(str(edited.value)) == Decimal("111"), "an edited row was overwritten"
    assert edited.is_edited
    assert Decimal(str(edited.catalog_value)) == master_of_3 + 25, "was/now must show the move"
    assert Decimal(str(untouched.value)) == Decimal("165") == Decimal(str(untouched.catalog_value)), (
        "an unedited row must follow"
    )


def test_reset_puts_the_master_price_back_and_stops_protecting_the_row(db, estimate):
    _build(db, estimate, "mono_slab_fixture")
    row = _row(db, estimate.id, "mix", 3)
    master = Decimal(str(row.catalog_value))
    pb.set_price(db, row, value=Decimal("111"))
    assert row.is_edited

    pb.set_price(db, row, reset=True)
    assert not row.is_edited
    assert Decimal(str(row.value)) == master

    # Setting the master number BY HAND is still a decision — still protected.
    pb.set_price(db, row, value=master)
    assert row.is_edited


def test_a_catalog_item_added_after_the_pull_is_unpriced_until_the_next_pull(db, estimate):
    """
    "Once a sheet exists, it is the only source." A new master item is not
    silently priced at today's catalog on an old job — it is unpriced there,
    the drift check lists it as `new`, and a pull adds it.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    mix_id = _mix_on(db, section.id)
    db.delete(_row(db, estimate.id, "mix", mix_id))     # simulate: mix not on the sheet
    db.flush()
    recalc_section(db, section); db.flush()

    unpriced = db.execute(text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
                          {"i": str(section.id)}).scalar()
    assert any(u.endswith("— mix") for u in unpriced), unpriced
    assert any(n["ref_id"] == mix_id for n in pb.drift(db, estimate.id).new)

    pb.pull_prices(db, estimate.id)
    recalc_section(db, section); db.flush()
    unpriced = db.execute(text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
                          {"i": str(section.id)}).scalar()
    assert unpriced == []


def test_a_rule_change_still_reaches_a_priced_estimate(db, estimate, setting):
    """
    Prices freeze. Rules do not. Waste is a rule — a correction to how the work
    is computed — and an old estimate must pick it up on recalc.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    before = _cost(db, section.id)
    db.execute(text("UPDATE estimate_sections SET waste_concrete = 0.20 WHERE id = :i"),
               {"i": str(section.id)})
    db.flush(); db.refresh(section)
    recalc_section(db, section); db.flush()
    assert _cost(db, section.id) > before


# ------------------------------------------------------ the coverage guard ----


def test_the_guard_fires_when_a_costing_lookup_runs_outside_any_book(db):
    """
    The forgotten call site, made loud. Under ESTIMATING_STRICT_PRICES=1 (set by
    conftest) a costing-side price lookup with no `priced_as` context raises,
    so a site nobody threaded the book to is a red test — not a job that
    silently reprices at today's catalog next March.
    """
    from app.services.costing import _find_material, _mix_unit_cost

    with pytest.raises(pb.NoPriceBook):
        _mix_unit_cost(db, 3)
    with pytest.raises(pb.NoPriceBook):
        _find_material(db, "SAND")

    # ...and says so explicitly when the catalog IS what you mean.
    with pb.catalog_only():
        assert _find_material(db, "SAND") is not None


def test_the_guard_is_quiet_in_production(db, monkeypatch):
    """Off strict, the same lookup is the catalog behaviour the app had before
    sql/048 — nothing gets worse; it just cannot silently get better."""
    from app.services.costing import _mix_unit_cost

    monkeypatch.delenv("ESTIMATING_STRICT_PRICES", raising=False)
    _price_mix(db, 3, "150")
    assert _mix_unit_cost(db, 3) == Decimal("150")


# ---------------------------------------------------------------- the API ----


def test_creating_an_estimate_pulls_its_sheet(client, db, project):
    r = client.post("/api/estimates", json={"project_id": str(project.id), "name": "auto-pull"})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    sheet = client.get(f"/api/estimates/{eid}/prices").json()
    assert sheet["rows"], "a new estimate must not be unpriced"
    assert sheet["edited"] == 0
    assert sheet["drift"]["drift"] == 0


def test_the_sheet_endpoint_edits_pulls_and_reports_drift(client, db, estimate):
    section = _build(db, estimate, "mono_slab_fixture")
    before = _cost(db, section.id)
    sheet = client.get(f"/api/estimates/{estimate.id}/prices").json()
    mix_id = _mix_on(db, section.id)
    row = next(r for r in sheet["rows"] if r["kind"] == "mix" and r["ref_id"] == mix_id)

    # edit → recalcs
    r = client.patch(f"/api/estimates/{estimate.id}/prices/{row['id']}",
                     json={"value": float(Decimal(row["value"]) - 10), "note": "SRM 9/2"})
    assert r.status_code == 200, r.text
    assert r.json()["is_edited"] is True
    assert _cost(db, section.id) < before

    # master moves → drift, dry run applies nothing
    db.execute(text("UPDATE mix_designs SET unit_cost = unit_cost + 5")); db.flush()
    d = client.post(f"/api/estimates/{estimate.id}/prices/pull?dry_run=true").json()
    assert d["applied"] is False and d["drift"] > 0
    assert any(c["ref_id"] == mix_id for c in d["conflicts"]), "the edited mix must be a conflict"

    # apply → unedited follow, the edited one is kept
    r = client.post(f"/api/estimates/{estimate.id}/prices/pull").json()
    assert r["applied"] is True
    after = client.get(f"/api/estimates/{estimate.id}/prices").json()
    kept = next(x for x in after["rows"] if x["id"] == row["id"])
    assert Decimal(kept["value"]) == Decimal(row["value"]) - 10
    assert after["drift"]["drift"] == 0 or all(c["ref_id"] == mix_id for c in after["drift"]["conflicts"])

    # reset → follows again
    r = client.patch(f"/api/estimates/{estimate.id}/prices/{row['id']}", json={"reset": True})
    assert r.status_code == 200 and r.json()["is_edited"] is False


def test_a_zero_price_is_refused(client, db, estimate):
    """A $0 mix is decision 5. (A zero RATE is allowed — test_price_sheet_rates.)"""
    _build(db, estimate, "mono_slab_fixture")
    sheet = client.get(f"/api/estimates/{estimate.id}/prices").json()
    mix = next(r for r in sheet["rows"] if r["kind"] == "mix")
    r = client.patch(f"/api/estimates/{estimate.id}/prices/{mix['id']}", json={"value": 0})
    assert r.status_code == 400
    assert client.patch(f"/api/estimates/{estimate.id}/prices/{mix['id']}", json={"value": -5}).status_code == 422


def test_the_quote_comparison_reads_the_sheet_not_the_catalog(client, db, estimate):
    """
    "What would we have charged" means at THIS JOB's prices. A negotiated bar
    price on the sheet is the baseline the quote is judged against, or every
    quote on a job with a good steel deal reads as off-band.
    """
    from app.services import quotes as qt
    from app.services.costing import catalog_cost_for_quote

    section = _build(db, estimate, "mono_slab_fixture")
    at_catalog = catalog_cost_for_quote(db, section, qt.REBAR)

    for p in pb.sheet_rows(db, estimate.id):
        if p.kind == "material" and "REBAR" in p.label.upper():
            pb.set_price(db, p, value=Decimal(str(p.value)) * 2)
    recalc_section(db, section); db.flush()

    at_sheet = catalog_cost_for_quote(db, section, qt.REBAR)
    assert abs(at_sheet - at_catalog * 2) <= Decimal("0.01"), (at_sheet, at_catalog)
