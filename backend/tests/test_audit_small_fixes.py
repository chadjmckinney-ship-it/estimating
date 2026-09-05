"""
Four audit items (docs/specs/audit-2026-09-02.md #5, #7, #8, #9), fixed together
on 2026-09-02 after the price sheet landed. None was costing the live job
money; each was a trap for the next section.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services import price_book as pb
from app.services.costing import (
    refresh_pour_costs,
    resolve_vapor_barrier,
    section_unpriced,
    vapor_barrier_fallback,
    vapor_barrier_source,
)
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.recalc import recalc_section


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate, mod_name, *, type_supervision=True):
    import importlib

    mod = importlib.import_module(f"tests.{mod_name}")
    section = mod.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    if type_supervision and hasattr(mod, "type_the_supervision"):
        mod.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _unpriced(db, section_id) -> list[str]:
    return db.execute(
        text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


# ------------------------------------------------ #7 SLAB CHAIRS on columns ----


def test_columns_buys_slab_chairs_not_metal_chairs(db, estimate):
    """The line says SLAB CHAIRS ($27); it was buying METAL CHAIRS 2.5" ($45)
    because it asked the catalog for "CHAIRS" and sort order decided."""
    section = _build(db, estimate, "columns_fixture")
    lines = {ln["code"]: ln for ln in load_stored_forming(db, section.id)["lines"]}
    chairs = lines["chairs"]
    assert chairs["label"] == "SLAB CHAIRS"
    catalog = db.execute(
        text("SELECT unit_cost FROM materials WHERE name ILIKE 'SLAB CHAIRS%' ORDER BY sort_order, id LIMIT 1")
    ).scalar()
    assert Decimal(str(chairs["unit_cost"])) == Decimal(str(catalog))
    assert Decimal(str(chairs["unit_cost"])) != Decimal("45")


# ---------------------------------------- #8 the vapor barrier fallback ----


def test_the_fallback_never_leaves_the_vapor_barrier_category(db):
    """`POLY 10 mil 20 x 100 Black` is site poly at $105 in `site_accessories`.
    It matched "10 mil" + "20" by name and priced a bid's vapor barrier at a
    third of the Yellow Guard it was bid on (sql/030, audit #8) — and it was
    still the live fallback because the company default is 0."""
    with pb.catalog_only():
        mat = vapor_barrier_fallback(db)
    assert mat is not None
    assert mat["category"] == "vapor_barrier", mat
    assert "Black" not in mat["name"]


def test_a_section_with_no_choice_and_no_default_says_where_its_roll_came_from(client, db, estimate):
    """...and says it through the totals endpoint, which the picker reads —
    the resolved name never reached the screen before (schema drop #4)."""
    section = _build(db, estimate, "mono_slab_fixture")
    chosen = section.vapor_barrier_material_id
    assert chosen and vapor_barrier_source(section, db) == "section"
    t = client.get(f"/api/mono-slabs/totals?section_id={section.id}").json()
    assert t["vapor_barrier_source"] == "section" and t["vapor_barrier"]

    db.execute(text("UPDATE system_settings SET value = '\"0\"'::jsonb WHERE key = 'default_vapor_barrier_material_id'"))
    section.vapor_barrier_material_id = None
    db.flush()
    t = client.get(f"/api/mono-slabs/totals?section_id={section.id}").json()
    assert t["vapor_barrier_source"] == "fallback"
    assert t["vapor_barrier"] and "Black" not in t["vapor_barrier"]

    db.execute(text("UPDATE system_settings SET value = to_jsonb(CAST(:v AS text)) WHERE key = 'default_vapor_barrier_material_id'"),
               {"v": str(chosen)})
    db.flush()
    assert client.get(f"/api/mono-slabs/totals?section_id={section.id}").json()["vapor_barrier_source"] == "default"


def test_no_vapor_barrier_at_all_is_unpriced_not_free(db, estimate):
    """Nothing chosen, no default, nothing in the category: poly is UNPRICED
    on the section, not quietly $0."""
    section = _build(db, estimate, "mono_slab_fixture")
    section.vapor_barrier_material_id = None
    db.execute(text("UPDATE system_settings SET value = '\"0\"'::jsonb WHERE key = 'default_vapor_barrier_material_id'"))
    db.execute(text("UPDATE materials SET is_active = false WHERE category = 'vapor_barrier'"))
    db.flush()
    with pb.priced_as(db, estimate.id):
        assert resolve_vapor_barrier(db, section) is None
        flagged = section_unpriced(db, section)
    assert any("vapor barrier — none chosen" in x for x in flagged), flagged


# --------------------------------- #5 supervision never typed → 0-day ladder ----


@pytest.mark.parametrize("mod", ["piers_fixture", "walls_fixture"])
def test_an_untyped_supervision_is_flagged_on_the_section(db, estimate, mod):
    """Piers and walls TYPE their days. Untyped, the rental ladder is 0 days
    and every machine reads $0.00 beside a correct rate — proven −$19,638.67
    on piers and −$14,403.10 on walls. The section now says so."""
    section = _build(db, estimate, mod, type_supervision=False)
    flagged = _unpriced(db, section.id)
    assert any("superintendent days — not typed" in x for x in flagged), flagged

    import importlib
    importlib.import_module(f"tests.{mod}").type_the_supervision(db, section.id)
    recalc_section(db, section); db.flush()
    assert not any("superintendent" in x for x in _unpriced(db, section.id))


def test_a_derived_supervision_is_never_flagged(db, estimate):
    """Mono slab and columns DERIVE their days; there is nothing to type."""
    for mod in ("mono_slab_fixture", "columns_fixture"):
        section = _build(db, estimate, mod)
        assert not any("superintendent" in x for x in _unpriced(db, section.id))


# --------------------------------------- #9 load_stored_equipment drivers ----


def test_stored_equipment_serves_the_real_paving_geometry(db, estimate):
    """The loader hand-built drivers from six summary columns and served a
    confident "0" for 9,537 LF of curb and 36,361 LF of joints. The live
    geometry now comes from equipment_drivers; the four figures the lines were
    priced with still come from the summary."""
    from app.schemas.estimate_equipment import EquipmentDrivers

    section = _build(db, estimate, "paving_fixture")
    stored = load_stored_equipment(db, section.id)
    d = EquipmentDrivers.model_validate(stored["drivers"])
    assert d.curb_lf > 0 and d.construction_joint_lf > 0 and d.control_joint_lf > 0
    assert d.total_sf > 0 and d.total_concrete_cy > 0


@pytest.mark.parametrize("mod,key", [("piers_fixture", "pier_count"), ("columns_fixture", "column_count")])
def test_stored_equipment_carries_the_assemblys_own_count(db, estimate, mod, key):
    from app.schemas.estimate_equipment import EquipmentDrivers

    section = _build(db, estimate, mod)
    d = EquipmentDrivers.model_validate(load_stored_equipment(db, section.id)["drivers"])
    assert getattr(d, key) > 0, f"{key} was dropped by the schema"


def test_stored_pricing_figures_come_from_the_summary(client, db, estimate):
    """Geometry live, pricing figures stored: the days the lines were priced
    with are the summary's, so the page explains the rows it shows."""
    from app.models.estimate_equipment import EstimateEquipmentSummary

    section = _build(db, estimate, "piers_fixture")
    summary = db.get(EstimateEquipmentSummary, section.id)
    r = client.get(f"/api/sections/{section.id}/equipment")
    assert r.status_code == 200
    d = r.json()["drivers"]
    assert Decimal(str(d["super_days"])) == Decimal(str(summary.super_days))
    assert Decimal(str(d["equip_days"])) == Decimal(str(summary.equip_days))
    assert int(d["pier_count"]) > 0


# ------------------------------- columns haul-off: a workbook artifact ----


def test_columns_haul_off_is_off_by_default_but_still_reachable(db, estimate):
    """
    Chad, 2026-09-02: "I think columns having hauloff is an artifact from
    building the workbook.. there shouldnt be hauloff.. and if there is, thats
    on us for a mistake or a CO.. but we will need it for pilasters."

    A column is formed off a footing someone else dug — no spoil. The line is
    on the 07 sheet, so it exists here; it is DISABLED rather than deleted
    because a pilaster is a columns section (sql/041) and a pilaster does dig.
    """
    section = _build(db, estimate, "columns_fixture")
    lines = {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}
    haul = lines["haul_off"]

    assert haul["enabled"] is False
    assert Decimal(str(haul["ext_cost"])) == 0
    # The rate is still there, so turning it on is one click, not a hunt.
    assert Decimal(str(haul["rate"])) > 0
    # ...and it is not flagged as unpriced: a disabled line costs nothing on
    # purpose, which is not the same as a line nobody could price.
    assert not any("HAUL" in x.upper() for x in _unpriced(db, section.id))


def test_turning_columns_haul_off_on_bills_it(client, db, estimate):
    """The pilaster / change-order path: tick it on, give it spoil, it costs."""
    section = _build(db, estimate, "columns_fixture")
    before = db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section.id)},
    ).scalar()

    r = client.patch(
        f"/api/sections/{section.id}/equipment/lines/haul_off",
        json={"enabled": True, "days_qty": 40},
    )
    assert r.status_code == 200, r.text

    lines = {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}
    haul = lines["haul_off"]
    assert haul["enabled"] is True
    assert Decimal(str(haul["ext_cost"])) == (
        Decimal("40") * Decimal(str(haul["rate"]))
    ).quantize(Decimal("0.01"))

    after = db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section.id)},
    ).scalar()
    assert after > before, "a change order that hauls spoil has to reach the bid"


def test_the_other_assemblies_keep_their_haul_off_enabled(db, estimate):
    """Piers and walls dig. Only columns is the artifact."""
    for mod in ("piers_fixture", "walls_fixture"):
        section = _build(db, estimate, mod)
        lines = {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}
        if "haul_off" in lines:
            assert lines["haul_off"]["enabled"] is True, mod
