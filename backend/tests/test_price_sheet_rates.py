"""
The estimate price sheet (sql/049) — stage 2: equipment and every monetary rate.

docs/specs/estimate-price-sheet-spec.md, "What is a price, and what is a rule".
Stage 1 froze mixes and materials per job. This stage freezes the rest of what
is a PRICE and lives in a table — equipment day rates, the company's labor
rates, sales tax, the fuel percentage, and each assembly's overrides of those —
while the RULES that share the same two tables stay live.

The first two tests are the ones that keep this honest: the split is a
hand-written list in two places (Python and the migration), and both have to
stay complete and equal. `labor_forming_sf` is $/SF; `nails_16p_per_sf` is SF
per box; nothing in the name tells them apart.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

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

SQL_049 = Path(__file__).resolve().parents[2] / "sql" / "049_price_sheet_rates.sql"


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


def _rate_row(db, estimate_id, key, scope=None) -> EstimatePrice | None:
    return db.scalars(
        select(EstimatePrice).where(
            EstimatePrice.estimate_id == estimate_id,
            EstimatePrice.kind == ("assembly_rate" if scope else "setting"),
            EstimatePrice.scope == scope,
            EstimatePrice.ref_key == key,
        )
    ).first()


def _labor_line(db, section_id, code):
    return db.execute(
        text("SELECT rate, qty, ext_cost FROM estimate_labor_lines "
             "WHERE section_id = :s AND code = :c"),
        {"s": str(section_id), "c": code},
    ).mappings().first()


# ------------------------------------------------------- the split itself ----


def test_every_rate_key_in_the_database_is_classified(db):
    """
    A key on neither list is a decision nobody made. This is the test that
    fails the day someone adds `labor_pump_hose_lf` to assembly_rates and
    does not say whether it is money.
    """
    keys = set(db.execute(text("SELECT key FROM system_settings")).scalars())
    keys |= set(db.execute(text("SELECT DISTINCT key FROM assembly_rates")).scalars())
    unclassified = sorted(k for k in keys if k not in pb.MONETARY_KEYS and k not in pb.RULE_KEYS)
    assert unclassified == [], f"decide price-or-rule for: {unclassified}"
    both = sorted(set(pb.MONETARY_KEYS) & pb.RULE_KEYS)
    assert both == [], f"on both lists: {both}"


def test_the_migrations_key_list_is_the_python_registry():
    """Two copies of one list. The migration backfilled with its copy; every
    later pull uses the Python one. They must not drift from each other."""
    src = SQL_049.read_text(encoding="utf-8")
    block = src.split("INSERT INTO monetary_keys (key, label, unit) VALUES", 1)[1].split(";", 1)[0]
    in_sql = dict(re.findall(r"\('([a-z_0-9]+)', '(?:[^']|'')*', '([A-Z ]+)'\)", block))
    assert set(in_sql) == set(pb.MONETARY_KEYS), (
        set(in_sql) ^ set(pb.MONETARY_KEYS)
    )
    for key, unit in in_sql.items():
        assert pb.MONETARY_KEYS[key][1] == unit, key


def test_the_eight_divisors_are_rules():
    """The traps named in the spec, pinned by name."""
    for key in ("nails_16p_per_sf", "nails_8p_per_sf", "lumber_2x4_per_sf", "lumber_ply_per_sf",
                "support_rebar_lb_per_sf", "labor_tie_steel_free_lb_per_sf", "chairs_sf_per_bag",
                "form_release_sf_per_gal"):
        assert key in pb.RULE_KEYS and key not in pb.MONETARY_KEYS, key


# --------------------------------------------------------------- labor ----


def test_an_edited_day_rate_reaches_the_bid_and_only_this_jobs_bid(db, project):
    """"On this job the super is $475." Days × $50 more, on A and not on B."""
    from tests import mono_slab_fixture as mf

    a = Estimate(project_id=project.id, name="A"); db.add(a); db.flush()
    b = Estimate(project_id=project.id, name="B"); db.add(b); db.flush()
    sa = _build(db, a, "mono_slab_fixture")
    sb = _build(db, b, "mono_slab_fixture")
    assert _cost(db, sa.id) == _cost(db, sb.id) == mf.GOLDEN_COST["total_cost"]

    row = _rate_row(db, a.id, "labor_super_day_rate")
    assert Decimal(str(row.value)) == Decimal("425")
    pb.set_price(db, row, value=Decimal("475"), note="two supers' worth")
    recalc_estimate(db, a); db.flush()

    line = _labor_line(db, sa.id, "superintendent")
    assert Decimal(str(line["rate"])) == Decimal("475")
    expected = Decimal("50") * mf.SUPER_DAYS
    assert abs((_cost(db, sa.id) - _cost(db, sb.id)) - expected) <= Decimal("0.02"), expected
    assert _cost(db, sb.id) == mf.GOLDEN_COST["total_cost"]


def test_an_assembly_override_on_the_sheet_beats_the_company_row(db, estimate):
    """
    Paving forms at $0.30 against the company's $0.45 (sql/035). The sheet
    keeps both levels, so the pull reproduces it — and editing the PAVING row
    moves paving without touching the company number.
    """
    section = _build(db, estimate, "paving_fixture")
    company = _rate_row(db, estimate.id, "labor_forming_sf")
    paving = _rate_row(db, estimate.id, "labor_forming_sf", scope="paving")
    assert company is not None and paving is not None
    assert Decimal(str(paving.value)) == Decimal("0.30")
    assert Decimal(str(company.value)) == Decimal("0.45")
    assert Decimal(str(_labor_line(db, section.id, "forming")["rate"])) == Decimal("0.30")

    before = _cost(db, section.id)
    pb.set_price(db, paving, value=Decimal("0.40"))
    recalc_section(db, section); db.flush()
    line = _labor_line(db, section.id, "forming")
    assert Decimal(str(line["rate"])) == Decimal("0.40")
    assert _cost(db, section.id) - before == (Decimal("0.10") * Decimal(str(line["qty"]))).quantize(Decimal("0.01"))
    assert Decimal(str(_rate_row(db, estimate.id, "labor_forming_sf").value)) == Decimal("0.45")


def test_a_master_rate_change_does_not_move_a_priced_estimate_but_is_reported(db, estimate):
    """The 2026-08-31 incident, for rates. Two settings and one assembly row
    move; the section does not; the drift check names all three."""
    from tests import mono_slab_fixture as mf

    section = _build(db, estimate, "mono_slab_fixture")
    db.execute(text("UPDATE system_settings SET value = '\"500\"'::jsonb WHERE key = 'labor_super_day_rate'"))
    db.execute(text("UPDATE system_settings SET value = '\"0.0900\"'::jsonb WHERE key = 'sales_tax_pct'"))
    db.execute(text("UPDATE assembly_rates SET value = 9 WHERE kind = 'paving' AND key = 'labor_forming_sf'"))
    db.flush()
    recalc_section(db, section); db.flush()
    assert _cost(db, section.id) == mf.GOLDEN_COST["total_cost"]

    d = pb.drift(db, estimate.id)
    moved = {(c["kind"], c.get("scope"), c["ref_key"]) for c in d.changed}
    assert ("setting", None, "labor_super_day_rate") in moved
    assert ("setting", None, "sales_tax_pct") in moved
    assert ("assembly_rate", "paving", "labor_forming_sf") in moved


def test_a_zero_rate_is_a_statement_not_an_error(db, estimate):
    """Paving pumps nothing; sidewalk has no curb labor. Both tables carry
    zeros and a pull must copy them — and the sheet must accept one typed."""
    _build(db, estimate, "paving_fixture")
    pump = _rate_row(db, estimate.id, "concrete_pump_cy", scope="paving")
    assert pump is not None and Decimal(str(pump.value)) == 0
    pb.set_price(db, pump, value=Decimal("12"))
    pb.set_price(db, pump, value=Decimal("0"))          # allowed
    assert pump.is_edited and Decimal(str(pump.value)) == 0

    machine = db.scalars(select(EstimatePrice).where(
        EstimatePrice.estimate_id == estimate.id, EstimatePrice.kind == "equipment")).first()
    with pytest.raises(ValueError):
        pb.set_price(db, machine, value=Decimal("0"))    # a $0 machine is decision 5


# ----------------------------------------------------------- sales tax ----


def test_the_tax_rate_is_pulled_but_the_exemption_stays_live(db, estimate):
    """Judgment call from the spec: the RATE is part of what was bid; the
    tri-state exemption is a rule about the project and is not frozen."""
    from app.services.costing import tax_rate_for

    section = _build(db, estimate, "mono_slab_fixture")
    assert tax_rate_for(db, section) == Decimal("0.0825")

    row = _rate_row(db, estimate.id, "sales_tax_pct")
    pb.set_price(db, row, value=Decimal("0.0700"))
    assert tax_rate_for(db, section) == Decimal("0.07")

    db.execute(text("UPDATE estimate_sections SET tax_exempt = true WHERE id = :i"), {"i": str(section.id)})
    db.flush(); db.refresh(section)
    assert tax_rate_for(db, section) == Decimal("0"), "exemption is a rule, still live"


# ----------------------------------------------------------- equipment ----


def test_a_machine_prices_off_the_sheet_and_a_catalog_change_does_not_reach_it(db, estimate):
    from tests import columns_fixture as cf

    section = _build(db, estimate, "columns_fixture")
    before = _cost(db, section.id)
    sky = db.scalars(select(EstimatePrice).where(
        EstimatePrice.estimate_id == estimate.id, EstimatePrice.kind == "equipment",
        EstimatePrice.label.ilike("SkyTrack%"))).first()
    assert sky is not None

    db.execute(text("UPDATE equipment SET unit_cost = unit_cost * 3 WHERE id = :i"), {"i": sky.ref_id})
    db.flush()
    eq = refresh_and_store_equipment(db, section.id)
    line = next(ln for ln in eq["lines"] if ln["code"] == "skytrack")
    assert line["price_source"] == "sheet"
    assert Decimal(str(line["rate"])) == Decimal(str(sky.value))
    recalc_section(db, section); db.flush()
    assert _cost(db, section.id) == before
    assert any(c["kind"] == "equipment" and c["ref_id"] == sky.ref_id for c in pb.drift(db, estimate.id).changed)


def test_an_edited_day_rate_on_a_machine_reaches_the_line(db, estimate):
    section = _build(db, estimate, "columns_fixture")
    sky = db.scalars(select(EstimatePrice).where(
        EstimatePrice.estimate_id == estimate.id, EstimatePrice.kind == "equipment",
        EstimatePrice.label.ilike("SkyTrack%"))).first()
    pb.set_price(db, sky, value=Decimal("999"))
    eq = refresh_and_store_equipment(db, section.id)
    line = next(ln for ln in eq["lines"] if ln["code"] == "skytrack")
    assert Decimal(str(line["rate"])) == Decimal("999")


def test_a_zero_priced_machine_on_the_master_list_is_unpriced(db, project):
    """`_equip_price` never took $0 as a price; the pull agrees."""
    fresh = Estimate(project_id=project.id, name="no sheet yet"); db.add(fresh); db.flush()
    db.execute(text("UPDATE equipment SET unit_cost = 0 WHERE name ILIKE 'SkyTrack%'"))
    db.flush()
    result = pb.pull_prices(db, fresh.id)
    assert any(u["kind"] == "equipment" and u["label"] == "SkyTrack" for u in result.unpriced)
    assert not any(p.kind == "equipment" and p.label == "SkyTrack"
                   for p in pb.sheet_rows(db, fresh.id))


# ----------------------------------------------------------------- rules ----


def test_a_rule_change_still_reaches_a_priced_estimate(db, estimate):
    """form_percent is how much of the edge gets formed — a rule. Changing it
    on the master list must move a priced job on recalc."""
    section = _build(db, estimate, "mono_slab_fixture")
    before = _cost(db, section.id)
    assert _rate_row(db, estimate.id, "form_percent") is None, "a rule must not be on the sheet"
    db.execute(text("UPDATE estimate_sections SET form_percent = NULL WHERE id = :i"), {"i": str(section.id)})
    db.execute(text("UPDATE system_settings SET value = '\"1.0\"'::jsonb WHERE key = 'form_percent'"))
    db.flush(); db.refresh(section)
    recalc_section(db, section); db.flush()
    assert _cost(db, section.id) != before


# ----------------------------------------------------------------- guard ----


def test_the_guard_covers_rates_and_ignores_rules(db):
    from app.services.calc import _rate_numeric

    with pytest.raises(pb.NoPriceBook):
        _rate_numeric(db, "paving", "labor_forming_sf", Decimal("0"))
    # a rule read outside any book is fine — rules are never on the sheet
    assert _rate_numeric(db, "paving", "waste_concrete", Decimal("0")) == Decimal("0.06")


# ------------------------------------------------------------------- API ----


def test_the_sheet_carries_the_new_kinds_and_edits_them(client, db, estimate):
    section = _build(db, estimate, "mono_slab_fixture")
    before = _cost(db, section.id)
    sheet = client.get(f"/api/estimates/{estimate.id}/prices").json()
    kinds = {r["kind"] for r in sheet["rows"]}
    assert {"mix", "material", "equipment", "setting", "assembly_rate"} <= kinds

    sup = next(r for r in sheet["rows"] if r["kind"] == "setting" and r["ref_key"] == "labor_super_day_rate")
    r = client.patch(f"/api/estimates/{estimate.id}/prices/{sup['id']}", json={"value": 475})
    assert r.status_code == 200, r.text
    assert _cost(db, section.id) > before

    # zero: fine on a rate, refused on a machine
    pump = next(r for r in sheet["rows"] if r["kind"] == "assembly_rate" and r["ref_key"] == "concrete_pump_cy")
    assert client.patch(f"/api/estimates/{estimate.id}/prices/{pump['id']}", json={"value": 0}).status_code == 200
    machine = next(r for r in sheet["rows"] if r["kind"] == "equipment")
    assert client.patch(f"/api/estimates/{estimate.id}/prices/{machine['id']}", json={"value": 0}).status_code == 400
