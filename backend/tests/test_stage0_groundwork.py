"""
Price-sheet stage 0: the groundwork, pinned.

docs/specs/estimate-price-sheet-spec.md, "Stage 0, concretely". Five of Chad's
decisions, each with a test that would have failed the day before it landed.

The headline — decision 5, in his words: "I dont like concrete prices starting
@ $0." Until sql/047 a NULL master price multiplied through as zero and vanished
into the total. A fresh install bid $324k of LBJ concrete at nothing and 425
tests stayed green, because zero is a perfectly plausible number to multiply by.
Nothing here stops the arithmetic from multiplying by zero — it has no other
option — but everything here makes sure the section SAYS SO.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.costing import section_unpriced
from app.services.material_costs import section_material_costs
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


ASSEMBLIES = [
    ("slab",    "mono_slab_fixture"),
    ("paving",  "paving_fixture"),
    ("piers",   "piers_fixture"),
    ("walls",   "walls_fixture"),
    ("columns", "columns_fixture"),
    # Absent until 2026-09-04 (audit P2 #9): the largest section on the job
    # was in none of the four matrices, contrary to the docstring above.
    ("deck",    "deck_fixture"),
]


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()




def _unprice(db, estimate_id, kind: str, where: str = "TRUE", **params) -> None:
    """
    Take a price OFF the estimate's sheet.

    Since sql/048 an estimate prices from its own sheet, so NULLing the master
    list changes nothing on a priced job — that is the feature. "Unpriced"
    means the SHEET has no row for it, which is what a pull leaves behind for
    a master item with no price.
    """
    db.execute(
        text(f"DELETE FROM estimate_prices WHERE estimate_id = :e AND kind = :k AND ({where})"),
        {"e": str(estimate_id), "k": kind, **params},
    )
    db.flush()


def _unpriced(db, section_id) -> list[str]:
    return db.execute(
        text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


# --------------------------------------------- decision 5: never $0, loudly ----


@pytest.mark.parametrize("name,mod", ASSEMBLIES, ids=[a[0] for a in ASSEMBLIES])
def test_a_priced_section_reports_nothing_unpriced(db, estimate, name, mod):
    """The quiet case has to be quiet, or nobody reads the loud one."""
    section = _build(db, estimate, mod)
    assert _unpriced(db, section.id) == [], (
        f"{name}: a fully priced fixture reported unpriced items: "
        f"{_unpriced(db, section.id)}"
    )


@pytest.mark.parametrize("name,mod", ASSEMBLIES, ids=[a[0] for a in ASSEMBLIES])
def test_an_unpriced_mix_is_named_on_the_section(db, estimate, name, mod):
    """
    NULL the master price under every mix on the section. The total goes
    light — arithmetic has no alternative — and the section must say WHICH mix
    it could not price, by name, on every assembly.
    """
    section = _build(db, estimate, mod)
    before = _cost(db, section.id)

    _unprice(db, estimate.id, "mix")
    recalc_section(db, section)
    db.flush()

    after = _cost(db, section.id)
    assert after < before, f"{name}: NULLing the mix did not move the total — nothing was priced"

    named = _unpriced(db, section.id)
    assert named, f"{name}: the section went ${before - after} light and said nothing"
    assert any(item.endswith("— mix") for item in named), named
    # The name is the mix's code, not an id — a reader should not need the
    # catalog open to know what is missing.
    codes = db.execute(text("SELECT code FROM mix_designs")).scalars().all()
    assert any(any(item.startswith(c) for c in codes) for item in named), named


def test_the_walls_footing_mix_is_checked_separately(db, estimate):
    """Two mixes on one section. Only the footing's goes NULL; only it is named."""
    section = _build(db, estimate, "walls_fixture")
    footing_mix = section.footing_mix_design_id
    assert footing_mix, "walls fixture should name a footing mix"

    _unprice(db, estimate.id, "mix", "ref_id = :i", i=footing_mix)
    recalc_section(db, section)
    db.flush()

    named = _unpriced(db, section.id)
    assert len(named) == 1, named
    code = db.execute(text("SELECT code FROM mix_designs WHERE id = :i"), {"i": footing_mix}).scalar()
    assert named[0] == f"{code} — mix"


def test_an_unpriced_mix_reaches_the_material_breakdown(db, estimate):
    """
    The stat card reads its dollars off the breakdown. A line with an unpriced
    item must say `source: unpriced`, name the item, and WITHHOLD its unit
    cost — a blended $/CY that quietly averaged in a zero is a lie.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    _unprice(db, estimate.id, "mix")
    recalc_section(db, section)
    db.flush()

    lines = {ln["key"]: ln for ln in section_material_costs(db, section)["lines"]}
    concrete = lines["concrete"]
    assert concrete["source"] == "unpriced"
    assert concrete["unpriced"], concrete
    assert concrete["unit_cost"] is None, "a blended rate over a zero is not a rate"
    assert "UNPRICED" in (concrete["detail"] or "")
    # Everything else on the section is still honestly priced.
    assert lines["rebar"]["source"] == "catalog"
    assert lines["rebar"]["unpriced"] == []


def test_a_mix_nobody_chose_is_reported_as_such(db, estimate):
    """
    A pour with mix_design_id NULL is not "priced at $0" — it is a pour with no
    mix. The label says that, rather than pretending a catalog row was consulted.
    """
    section = _build(db, estimate, "mono_slab_fixture")
    db.execute(text("UPDATE mono_slabs SET mix_design_id = NULL WHERE section_id = :s"),
               {"s": str(section.id)})
    db.flush()
    recalc_section(db, section)
    db.flush()
    assert "mix (none chosen) — mix" in _unpriced(db, section.id)


def test_an_unpriced_section_reaches_the_api(client, db, estimate):
    """`calc_unpriced` is read-model field; a read model built field by field
    drops what it does not name (the 2026-08-30 lesson)."""
    section = _build(db, estimate, "columns_fixture")
    _unprice(db, estimate.id, "mix")
    recalc_section(db, section)
    db.flush()

    r = client.get(f"/api/sections/{section.id}")
    assert r.status_code == 200, r.text
    assert r.json()["calc_unpriced"], "the API dropped calc_unpriced"

    listed = client.get(f"/api/estimates/{estimate.id}/sections").json()
    assert any(s["calc_unpriced"] for s in listed)


def test_a_quoted_steel_package_is_not_flagged_for_a_missing_catalog_price(db, estimate):
    """
    If the fabricator's number is on the section, the catalog's bar price is
    irrelevant — flagging it would teach people that the banner cries wolf.
    """
    from app.models.section_quote import SectionQuote

    section = _build(db, estimate, "walls_fixture")
    _unprice(db, estimate.id, "material", "label ILIKE 'REBAR%'")
    db.add(SectionQuote(section_id=section.id, kind="rebar",
                        amount=Decimal("21000"), unit="LS", baseline_qty=Decimal("1")))
    db.flush()
    recalc_section(db, section)
    db.flush()
    assert not any("rebar" in x for x in _unpriced(db, section.id)), _unpriced(db, section.id)


# ------------------------------------------------ 0e: equipment, same rule ----


def test_a_zero_catalog_price_on_a_machine_falls_through(db, estimate):
    """
    The audit's P3 finding. `_equip_rate` used `is not None`, so a $0.00 row
    priced a machine at nothing — zeroing MINI EXCAVATOR took the columns
    hoisting line to $0.00 while the identical machine on walls fell back to
    $475. A zero is not a price.
    """
    from app.services.estimate_equipment import get_or_refresh_equipment

    section = _build(db, estimate, "columns_fixture")
    db.execute(text("UPDATE equipment SET unit_cost = 0 WHERE name ILIKE 'MINI EXCAVATOR%'"))
    db.flush()
    from app.services.estimate_equipment import refresh_and_store_equipment

    eq = refresh_and_store_equipment(db, section.id)
    hoist = next(ln for ln in eq["lines"] if ln["code"] == "hoisting")
    assert Decimal(str(hoist["rate"])) > 0, "a $0 catalog row priced the hoist at nothing"


def test_a_rental_priced_from_a_code_default_is_flagged(db, estimate):
    """
    No catalog price, no assembly rate → the number is a literal from
    estimate_equipment.py. That is a placeholder, not a price, and the line
    and the section both have to say so.
    """
    from app.services.estimate_equipment import refresh_and_store_equipment

    section = _build(db, estimate, "columns_fixture")
    # Off the SHEET (sql/049) — the machine and any rate row for it. NULLing
    # the catalog alone would change nothing on a pulled job.
    _unprice(db, estimate.id, "equipment", "label ILIKE 'SkyTrack%'")
    _unprice(db, estimate.id, "assembly_rate", "ref_key = 'equip_skytrack_day_rate'")
    _unprice(db, estimate.id, "setting", "ref_key = 'equip_skytrack_day_rate'")

    eq = refresh_and_store_equipment(db, section.id)
    sky = next(ln for ln in eq["lines"] if ln["code"] == "skytrack")
    assert sky["price_source"] == "default"
    assert sky["missing_price"] is True
    assert "SKY TRACK" in eq["missing_prices"]

    recalc_section(db, section)
    db.flush()
    assert any("SKY TRACK" in x and "equipment" in x for x in _unpriced(db, section.id)), (
        _unpriced(db, section.id)
    )


def test_a_catalog_priced_rental_says_so(db, estimate):
    from app.services.estimate_equipment import refresh_and_store_equipment

    section = _build(db, estimate, "columns_fixture")
    eq = refresh_and_store_equipment(db, section.id)
    for ln in eq["lines"]:
        if ln["group_name"] == "equipment" and ln.get("equipment_id"):
            # "sheet" since sql/049: the catalog price, as pulled onto this job.
            assert ln["price_source"] == "sheet", ln
            assert ln["missing_price"] is False, ln
    assert eq["missing_prices"] == []


# ---------------------------------------------------- decision 1: dropped ----


def test_mix_prices_and_supplier_bids_are_gone(db):
    """
    Decision 1. `mix_prices` was a per-supplier dated history with one reader
    that ignored the date and took min() — a 2019 quote would have won. Chad
    wants one master price per mix, which is `mix_designs.unit_cost`.
    """
    tables = set(db.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )).scalars())
    assert "mix_prices" not in tables
    assert "supplier_bids" not in tables
    assert "concrete_suppliers" in tables, "the supplier list itself stays"


def test_the_mix_design_api_no_longer_carries_supplier_prices(client):
    r = client.get("/api/mix-designs")
    assert r.status_code == 200
    assert r.json(), "catalog should have mixes"
    assert "prices" not in r.json()[0]
    assert client.get("/api/mix-prices").status_code == 404


# ------------------------------------------ decision 4: the sidewalk row ----


def test_sidewalk_prices_accessories_from_the_catalog_like_paving(db, estimate):
    """
    The last `*_unit_cost` row in assembly_rates, a survivor of sql/044.
    Chad: "someone edited a formula in the workbook and wasnt caught."
    """
    from app.services.forming import calc_forming_materials

    row = db.execute(text(
        "SELECT 1 FROM assembly_rates WHERE kind = 'sidewalk' AND key = 'accessories_unit_cost'"
    )).scalar()
    assert row is None, "sql/047 did not delete the sidewalk row"

    section = _build(db, estimate, "paving_fixture")
    paving = {ln["code"]: ln for ln in calc_forming_materials(db, section.id)["lines"]}
    section.kind = "sidewalk"
    db.flush()
    sidewalk = {ln["code"]: ln for ln in calc_forming_materials(db, section.id)["lines"]}
    assert sidewalk["accessories"]["unit_cost"] == paving["accessories"]["unit_cost"]
    assert sidewalk["accessories"]["price_source"] == "catalog"


# --------------------------------------- the four promoted source literals ----


@pytest.mark.parametrize("kind_mod,code,catalog_name", [
    ("paving_fixture", "haul_off",      "CONCRETE HAUL OFF"),
    ("paving_fixture", "texture_comb",  "TEXTURE COMB"),
    ("paving_fixture", "dowel_baskets", "DOWEL BASKETS"),
    ("piers_fixture",  "haul_off",      "CONCRETE HAUL OFF"),
    ("walls_fixture",  "haul_off",      "CONCRETE HAUL OFF"),
    ("walls_fixture",  "pipe_brace",    "PIPE BRACING"),
])
def test_a_promoted_line_prices_from_the_catalog_by_name(db, estimate, kind_mod, code, catalog_name):
    """
    Four lines priced from Python literals because the catalog had no row to
    land on. Now it does, and the line names it — the Yellow Guard rule.
    """
    from app.services.forming import calc_forming_materials

    section = _build(db, estimate, kind_mod)
    lines = {ln["code"]: ln for ln in calc_forming_materials(db, section.id)["lines"]}
    ln = lines[code]
    assert ln["price_source"] == "catalog", ln
    assert ln["material_name"] == catalog_name, ln
    assert ln["unit_cost"] is not None


def test_a_promoted_line_with_no_catalog_row_is_unpriced_not_priced_from_source(db, estimate):
    """
    The literal is gone. Deactivate the catalog row and the line must read
    unpriced — the day it silently reverts to $250 from a Python file is the
    day a price lives in code again.
    """
    from app.services.forming import calc_forming_materials

    section = _build(db, estimate, "walls_fixture")
    db.execute(text("UPDATE materials SET is_active = false WHERE name = 'CONCRETE HAUL OFF'"))
    _unprice(db, estimate.id, "material", "label = 'CONCRETE HAUL OFF'")
    lines = {ln["code"]: ln for ln in calc_forming_materials(db, section.id)["lines"]}
    haul = lines["haul_off"]
    assert haul["unit_cost"] is None
    assert haul["missing_price"] is True
    assert haul["price_source"] is None


def test_a_catalog_row_the_sheet_has_no_price_for_is_unpriced_not_priced_from_the_workbook(
    db, estimate
):
    """
    The other half of the rule above, still open on 2026-09-04 (audit P2 #4).

    `forming._line` priced from its workbook literal whenever the resolved row
    carried no price — and on a sheeted estimate that is exactly what a row
    the sheet holds nothing for looks like: an item added to the catalog after
    the pull, or one the master list has no price for. Both are documented as
    UNPRICED and reported (decision 5). Instead the line extended at a 2025
    number with price_source="sheet", missing_price=False, and never reached
    the section's list.

    The 2x4 on the deck: the catalog row is there, this job's sheet says
    nothing, the literal says $0.859375. The literal loses.
    """
    from app.services.forming import calc_forming_materials, refresh_and_store_forming

    section = _build(db, estimate, "deck_fixture")
    _unprice(db, estimate.id, "material", "label ILIKE '2 X 4%'")

    lines = {ln["code"]: ln for ln in calc_forming_materials(db, section.id)["lines"]}
    ln = lines["2x4"]
    assert ln["material_name"], "the catalog row is still there — this is not the no-row case"
    assert Decimal(str(ln["qty"])) > 0
    assert ln["unit_cost"] is None and ln["ext_cost"] is None
    assert ln["missing_price"] is True
    assert ln["price_source"] is None

    # ...and the section says so, which is the whole point of the list. The
    # list reads the STORED lines, so store them the way opening the section
    # does, then re-cost.
    refresh_and_store_forming(db, section.id)
    recalc_section(db, section)
    db.flush()
    flagged = _unpriced(db, section.id)
    assert any(f"{ln['label']} — forming" in x for x in flagged), flagged
