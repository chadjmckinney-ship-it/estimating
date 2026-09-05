"""
Rates set on ONE section (sql/055) — and the ladder behind them.

Chad, 2026-09-04, asked for the company settings to be editable per estimate:

    "lets say a place and finish sub says for a project, he can do it for less
     because of the size of the pours.."

and, asked where the override should live: **"I think making rates changes per
section is what I would like the best"**, with the per-estimate layer kept
underneath.

Half of the ask already existed and had not been found — a PRICE has been
editable per job on the Prices screen since sql/048, scoped by assembly. What
was missing was that the sheet is per ESTIMATE: a job with two paving sections
could not say the sub is cheaper on the big pours and not the little ones. And
RULES had no per-job override anywhere.

## The ladder

    section_rates            this section, price or rule    <- beats everything
      price sheet            a PRICE, frozen at the pull
      estimate_rules         a RULE, this job, read live
        assembly_rates       what this assembly does
          system_settings    what the company does
            code default

## The two halves of this file

The **first** is that nothing moved. Every golden number in the suite already
proves it, but it is asserted here on its own so a future change to the ladder
fails with a name rather than in `test_columns_golden` with a number.

The **second** is that each rung beats the one below it, and that an override
reaches the stored takeoff and the section total rather than just the screen.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services import price_book as pb
from app.services.calc import _rate_numeric
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.recalc import recalc_section

D = Decimal


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
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    if hasattr(mod, "type_the_supervision"):
        mod.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _labor(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, section_id)["lines"]}


def _rates(client, section_id) -> dict[str, dict]:
    r = client.get(f"/api/sections/{section_id}/rates")
    assert r.status_code == 200, r.text
    return {row["key"]: row for row in r.json()["rows"]}


# ------------------------------------------------------- nothing moved ----


@pytest.mark.parametrize(
    "mod,golden",
    [
        ("columns_fixture", "tests.test_columns:APP"),
        ("deck_fixture", "tests.deck_fixture:GOLDEN_COST"),
    ],
)
def test_a_section_with_no_overrides_costs_exactly_what_it_did(db, estimate, mod, golden):
    """
    Two new tables and a new rung on the ladder every rate in the app reads,
    and not one number moves. Both tables ship EMPTY (sql/055) for exactly
    this reason.
    """
    import importlib

    mod_name, attr = golden.split(":")
    want = getattr(importlib.import_module(mod_name), attr)
    if isinstance(want, dict):
        want = want["total_cost"]

    section = _build(db, estimate, mod)
    assert _cost(db, section.id) == want


def test_the_ladder_with_nothing_overridden_is_the_old_ladder(db, estimate):
    """The resolution itself, not just the total. Paving forms at $0.30 from
    its assembly rate while the company says $0.45 — same as before sql/055."""
    section = _build(db, estimate, "paving_fixture")
    with pb.priced_as(db, estimate.id), pb.for_section(section.id):
        assert _rate_numeric(db, "paving", "labor_forming_sf", D("9")) == D("0.30")
        assert _rate_numeric(db, "mono_slab", "labor_forming_sf", D("9")) == D("0.45")


# --------------------------------------------------- each rung wins ----


def test_a_section_rate_beats_everything(client, db, estimate):
    """
    The top rung, and Chad's actual sentence. Place & finish on this section
    only — the job's sheet, the assembly and the company all say otherwise and
    all lose.
    """
    section = _build(db, estimate, "paving_fixture")
    before = _rates(client, section.id)["labor_place_finish_sf"]
    assert before["source"] in ("job", "assembly", "company")

    r = client.put(
        f"/api/sections/{section.id}/rates/labor_place_finish_sf",
        json={"value": "0.42", "note": "Ramirez — big pours"},
    )
    assert r.status_code == 200, r.text

    after = _rates(client, section.id)["labor_place_finish_sf"]
    assert after["source"] == "section"
    assert D(str(after["value"])) == D("0.42")
    assert after["note"] == "Ramirez — big pours"
    # ...and the layers it beat are still reported, so the screen can say what
    # it would fall back to.
    assert after["company_value"] is not None


def test_a_section_rate_reaches_the_stored_takeoff_and_the_total(client, db, estimate):
    """
    Not just the screen. The rate has to move the stored labor line and the
    section total, which is what `_recost` on the write path is for — the
    lesson the columns router paid $436,826.42 for.
    """
    section = _build(db, estimate, "deck_fixture")
    before_cost = _cost(db, section.id)
    before_line = D(str(_labor(db, section.id)["place_finish"]["ext_cost"]))
    sf = D(str(_labor(db, section.id)["place_finish"]["qty"]))

    client.put(
        f"/api/sections/{section.id}/rates/labor_place_finish_sf",
        json={"value": "0.42"},
    )
    db.expire_all()

    after_line = D(str(_labor(db, section.id)["place_finish"]["ext_cost"]))
    assert after_line == (sf * D("0.42")).quantize(D("0.01"))
    # Labor is untaxed and carries no fuel, so the section moves by exactly the
    # difference — 32,100 SF x $0.08.
    assert _cost(db, section.id) == before_cost - (before_line - after_line)


def test_clearing_it_hands_the_rate_back(client, db, estimate):
    """
    A cleared override is DELETED, not blanked. There is no "unset" row in
    section_rates: a row means somebody decided, and no row means nobody did.
    """
    section = _build(db, estimate, "deck_fixture")
    before = _cost(db, section.id)

    client.put(
        f"/api/sections/{section.id}/rates/labor_place_finish_sf", json={"value": "0.42"}
    )
    db.expire_all()
    assert _cost(db, section.id) != before

    r = client.delete(f"/api/sections/{section.id}/rates/labor_place_finish_sf")
    assert r.status_code == 200, r.text
    db.expire_all()

    assert _cost(db, section.id) == before
    assert _rates(client, section.id)["labor_place_finish_sf"]["source"] != "section"
    assert db.execute(
        text("SELECT count(*) FROM section_rates WHERE section_id = :s"),
        {"s": str(section.id)},
    ).scalar() == 0


def test_two_sections_of_one_job_can_disagree(client, db, estimate):
    """
    The sentence the price sheet could not say. The sheet is per ESTIMATE, so
    editing "paving rates" there moved every paving section on the job; the
    thing that makes a sub cheaper is the size of THESE pours.
    """
    from tests import paving_fixture as pf

    a = _build(db, estimate, "paving_fixture")
    b = pf.build_section(db, estimate, pf.price_the_mix(db))
    refresh_and_store_forming(db, b.id)
    refresh_and_store_labor(db, b.id)
    refresh_and_store_equipment(db, b.id)
    refresh_pour_costs(db, b)
    db.flush()
    recalc_section(db, b)
    db.flush()

    b_before = _cost(db, b.id)
    client.put(f"/api/sections/{a.id}/rates/labor_place_finish_sf", json={"value": "0.20"})
    db.expire_all()

    assert _rates(client, a.id)["labor_place_finish_sf"]["source"] == "section"
    assert _rates(client, b.id)["labor_place_finish_sf"]["source"] != "section"
    assert _cost(db, b.id) == b_before, "the other section must not move"


def test_a_job_rule_beats_the_assembly_and_the_company(db, estimate):
    """
    The middle rung, and the one that had nowhere to live. A RULE cannot go on
    the price sheet — the sheet freezes, and a frozen rule would stop a
    correction reaching the jobs it was made for — so this is its own table,
    read live.
    """
    section = _build(db, estimate, "paving_fixture")
    with pb.priced_as(db, estimate.id), pb.for_section(section.id):
        assert _rate_numeric(db, "paving", "form_percent", D("9")) == D("1.0")

    db.execute(
        text("INSERT INTO estimate_rules (estimate_id, key, value) "
             "VALUES (:e, 'form_percent', 0.7)"),
        {"e": str(estimate.id)},
    )
    db.flush()
    with pb.priced_as(db, estimate.id), pb.for_section(section.id):
        assert _rate_numeric(db, "paving", "form_percent", D("9")) == D("0.7")


def test_a_section_rate_beats_a_job_rule_too(db, estimate):
    """The top rung is the top rung for rules as well as prices."""
    section = _build(db, estimate, "paving_fixture")
    db.execute(
        text("INSERT INTO estimate_rules (estimate_id, key, value) "
             "VALUES (:e, 'form_percent', 0.7)"),
        {"e": str(estimate.id)},
    )
    db.execute(
        text("INSERT INTO section_rates (section_id, key, value) "
             "VALUES (:s, 'form_percent', 0.35)"),
        {"s": str(section.id)},
    )
    db.flush()
    with pb.priced_as(db, estimate.id), pb.for_section(section.id):
        assert _rate_numeric(db, "paving", "form_percent", D("9")) == D("0.35")


def test_a_price_never_reads_the_rule_table(db, estimate):
    """
    Belt and braces on the split. A monetary key resolves through the price
    sheet; `estimate_rules` is not a second home for a price, and a row there
    for one must do nothing.
    """
    section = _build(db, estimate, "paving_fixture")
    db.execute(
        text("INSERT INTO estimate_rules (estimate_id, key, value) "
             "VALUES (:e, 'labor_forming_sf', 99)"),
        {"e": str(estimate.id)},
    )
    db.flush()
    with pb.priced_as(db, estimate.id), pb.for_section(section.id):
        assert _rate_numeric(db, "paving", "labor_forming_sf", D("9")) == D("0.30")


def test_outside_a_section_the_ladder_starts_one_rung_down(db, estimate):
    """
    `current_section()` is None for a catalog read or a bare helper call.
    Nothing breaks — the section rung is simply skipped, which is what lets
    every non-section caller in the app keep working unchanged.
    """
    section = _build(db, estimate, "paving_fixture")
    db.execute(
        text("INSERT INTO section_rates (section_id, key, value) "
             "VALUES (:s, 'form_percent', 0.35)"),
        {"s": str(section.id)},
    )
    db.flush()
    with pb.priced_as(db, estimate.id):
        assert _rate_numeric(db, "paving", "form_percent", D("9")) == D("1.0")


# ------------------------------------------------------ what it reports ----


def test_every_row_carries_the_whole_ladder(client, db, estimate):
    """
    The card's real job. A rate you cannot trace is a rate you cannot defend
    three months later, so every row reports each rung — not just the answer.
    """
    section = _build(db, estimate, "paving_fixture")
    row = _rates(client, section.id)["labor_forming_sf"]
    assert row["is_price"] is True
    assert row["unit"] == "SF"
    assert D(str(row["assembly_value"])) == D("0.30")
    assert D(str(row["company_value"])) == D("0.45")
    assert row["source"] in ("job", "assembly")
    assert row["was_read"] is True


def test_the_list_is_what_the_takeoff_actually_read(client, db, estimate):
    """
    Not a hand-kept list of "keys a paving section reads" — that would drift
    from the line sets the day somebody adds a line. The takeoff is run inside
    `recording_rates()` and the keys it asked for are the keys shown.
    """
    section = _build(db, estimate, "paving_fixture")
    rows = _rates(client, section.id)
    read = {k for k, r in rows.items() if r["was_read"]}
    # Things a paving section genuinely prices.
    assert {"labor_forming_sf", "labor_place_finish_sf", "form_percent"} <= read
    # ...and nothing a paving section has never heard of.
    assert "labor_gb_forming_ff" not in read


def test_an_unknown_key_is_refused(client, db, estimate):
    """Keys come from the registry. Inventing one here would store a number
    nothing reads — the same call the settings router makes."""
    section = _build(db, estimate, "paving_fixture")
    r = client.put(
        f"/api/sections/{section.id}/rates/not_a_real_rate", json={"value": "1"}
    )
    assert r.status_code == 400 and "not a rate" in r.text


# -------------------------------- labor per section, material per job ----
#
# Chad, 2026-09-04, stating the policy:
#
#     "I want all the rates editable per section, each section should be
#      separate from the others for labor... forming labor for slabs, paving,
#      CIP decks, etc is based on that section. materials should be standard
#      across the estimate. concrete and materials are quoted per job so should
#      be edited that way."


def test_concrete_and_catalog_materials_were_never_section_rates(client, db, estimate):
    """
    The half of the policy that needed no code. Mixes and materials are catalog
    rows on the price sheet, resolved by ref_id — they never come through
    `_rate_numeric`, so they could never have been set on a section and are not
    on this card at all.
    """
    section = _build(db, estimate, "deck_fixture")
    keys = set(_rates(client, section.id))
    assert not any(k.startswith("mix_") for k in keys)
    # The lumber the deck buys is a catalog row (2 X 4 X 16'), not a rate.
    assert "lumber_2x4_price" not in keys


def test_what_a_price_is_PER_decides_the_level(client, db, estimate):
    """
    The line that took two passes to find. The first cut said "a material is a
    material however it is priced" and put PT cable on the job. Chad,
    2026-09-04:

        "PT cables are section level, per sf on slabs is different the decks.
         also have done one a project that is townhomes and apartments and they
         had different pt spacing."

    So the test is not "is it a material" — it is **what is it priced PER**.
    Per unit of the WORK ($/SF of deck) varies with what is being built and is
    a section rate. Per unit of the MATERIAL ($/CY of sand) is the supplier's
    number for the job.
    """
    section = _build(db, estimate, "deck_fixture")
    rows = _rates(client, section.id)

    # Priced per SF of the work.
    for key in ("pt_cable_sf", "plywood_forming_sf", "carton_forms_sf",
                "reshoring_material_sf"):
        assert rows[key]["level"] == "section", key

    # Priced per unit of the material itself.
    assert rows["stud_rails_lb"]["level"] == "estimate"


def test_pt_can_differ_between_two_sections_of_one_job(client, db, estimate):
    """
    Chad's townhomes-and-apartments job. Both the PRICE ($/SF) and the SPACING
    (`pt_lb_per_sf`, the cable weight) are section-level, so one estimate can
    carry two buildings post-tensioned differently.
    """
    section = _build(db, estimate, "deck_fixture")
    before = _cost(db, section.id)

    r = client.put(
        f"/api/sections/{section.id}/rates/pt_cable_sf",
        json={"value": "1.10", "note": "deck package, not the slab price"},
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    # 32,100 SF x $0.35, plus the tax that rides a material.
    assert _cost(db, section.id) < before

    r = client.put(
        f"/api/sections/{section.id}/rates/pt_lb_per_sf", json={"value": "1.30"}
    )
    assert r.status_code == 200, r.text


def test_a_material_priced_per_unit_of_ITSELF_stays_on_the_job(client, db, estimate):
    """Sand is sand whichever section the truck backs up to."""
    section = _build(db, estimate, "deck_fixture")
    r = client.put(
        f"/api/sections/{section.id}/rates/stud_rails_lb", json={"value": "1.10"}
    )
    assert r.status_code == 400, r.text
    # Refused with somewhere to go, not just refused.
    assert "price sheet" in r.text and "Stud rails" in r.text


def test_labor_is_a_section_fact(client, db, estimate):
    """"forming labor for slabs, paving, CIP decks, etc is based on that
    section." Every labor key is settable here."""
    section = _build(db, estimate, "deck_fixture")
    rows = _rates(client, section.id)
    # Supervision DAY RATES are the job's, not the section's — Chad,
    # 2026-09-05: "supervision, equipment, materials are all project specific
    # pricing.. labor changes with each section." The days per section stay.
    supervision = {
        "labor_super_day_rate", "labor_foreman_day_rate",
        "labor_pm_day_rate", "labor_expense_day_rate",
    }
    labor = [k for k in rows if k.startswith("labor_") and k not in supervision]
    assert labor, "a deck reads labor rates"
    assert all(rows[k]["level"] == "section" for k in labor), [
        k for k in labor if rows[k]["level"] != "section"
    ]
    for k in supervision & set(rows):
        assert rows[k]["level"] == "estimate", k

    r = client.put(
        f"/api/sections/{section.id}/rates/labor_forming_sf", json={"value": "4.10"}
    )
    assert r.status_code == 200, r.text


def test_the_job_facts_are_not_section_facts(client, db, estimate):
    """Tax follows the project and the fuel uplift follows the company.
    Neither is a property of one section's work."""
    section = _build(db, estimate, "deck_fixture")
    # ...and since 2026-09-05 the supervision day rates, mobilization and the
    # equipment day rates: "supervision, equipment, materials are all project
    # specific pricing" — "mobilization and the equipment day rates are per job."
    for key in (
        "sales_tax_pct", "equip_fuel_maint_pct",
        "labor_super_day_rate", "mobilization_ls", "equip_crane_day_rate", "equip_misc_day_rate",
    ):
        r = client.put(f"/api/sections/{section.id}/rates/{key}", json={"value": "0.1"})
        assert r.status_code == 400, f"{key}: {r.text}"


def test_a_job_level_rate_is_still_SHOWN_on_the_section(client, db, estimate):
    """
    Read-only, not hidden. You still want to see what this section is paying
    for sand — hiding it would leave the card looking like the whole story
    when it is not.
    """
    section = _build(db, estimate, "deck_fixture")
    row = _rates(client, section.id)["stud_rails_lb"]
    assert row["level"] == "estimate"
    assert row["value"] is not None
    assert row["source"] in ("job", "assembly", "company", "default")
