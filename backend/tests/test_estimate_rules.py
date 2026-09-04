"""
Rules for this job — the screen `estimate_rules` never had.

The table and its resolution shipped with sql/055 and were tested there.
Setting one still took SQL, which meant the middle rung of the ladder was the
one nobody could reach:

    section_rates      this section                    <- had a card
      estimate_rules   THIS JOB                        <- had nothing
        assembly_rates what a paving section does      <- still has nothing
          system_settings  what S&S does               <- has a card
            code default

Chad's three calls, 2026-09-04:

  * the card lives on the ESTIMATE page, not buried in the price sheet — the
    per-job PRICE overrides sql/048 shipped sat 200 material rows down that
    page and went unfound for weeks
  * it lists **only what this job's sections read**
  * where a section answers a rule itself, the row SAYS SO rather than showing
    a job number that section never sees

That last one is the substance. Four rules — waste concrete/sand/rebar and
form % — are COLUMNS on `estimate_sections`, checked in `calc._waste` before
the ladder runs at all. A job rule for those reaches only the sections that
left the column blank. A screen that let you type a waste factor and did not
mention that two of four sections ignore it would be worse than no screen.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
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


def _rules(client, estimate) -> dict:
    r = client.get(f"/api/estimates/{estimate.id}/rules")
    assert r.status_code == 200, r.text
    body = r.json()
    return {row["key"]: row for row in body["rows"]}


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


# ------------------------------------------------------------- what it lists


def test_it_lists_what_the_sections_actually_read(client, db, estimate):
    """
    Not a hand-written list. The takeoff is RUN inside `recording_rates()` and
    the keys it asked for are the keys shown, so the card cannot drift from the
    line sets the way a maintained list would.
    """
    section = _build(db, estimate, "deck_fixture")
    rows = _rules(client, estimate)
    assert rows, "a deck section reads rules"
    # Read by the deck's takeoff, and recorded as such.
    for key in ("reshoring_multiplier", "form_rental_shoring_multiplier",
                "lumber_2x4_per_lf", "nails_edge_factor"):
        assert rows[key]["read_by"] == [section.name], key
    # Not read by any assembly on this job.
    assert "columns_per_super_week" not in rows
    assert "pier_cover_in" not in rows


def test_read_by_is_a_positive_signal_not_a_complete_one(client, db, estimate):
    """
    Only three passes replay without storing — forming, labor and equipment.
    The GEOMETRY pass does not, so `waste_concrete` comes back with an empty
    `read_by` on a deck that plainly reads it.

    It is still LISTED, because `assembly_rates` names it. The screen must not
    turn an empty `read_by` into "nothing reads this": that is the one rule an
    estimator most wants to set per job, and a false "not used" beside it would
    cost the whole card its credibility.
    """
    _build(db, estimate, "deck_fixture")
    rows = _rules(client, estimate)
    assert "waste_concrete" in rows
    assert rows["waste_concrete"]["read_by"] == []
    assert rows["waste_concrete"]["assembly_values"], "listed because the assembly names it"


def test_prices_are_not_on_this_card(client, db, estimate):
    """
    A price is FROZEN on the price sheet at the pull; a rule is read LIVE so a
    correction reaches the jobs it was made for. That split is the spine of the
    pricing design, and a price appearing on a "rules for this job" card would
    be an invitation to break it.
    """
    _build(db, estimate, "deck_fixture")
    rows = _rules(client, estimate)
    assert rows, "sanity"
    from app.services import price_book as pb

    assert not [k for k in rows if k in pb.MONETARY_KEYS]
    assert all(k in pb.RULE_KEYS for k in rows)


def test_a_second_section_adds_its_rules(client, db, estimate):
    """Adding a section adds its rules — no list to remember to update."""
    _build(db, estimate, "deck_fixture")
    deck_only = set(_rules(client, estimate))
    _build(db, estimate, "piers_fixture")
    both = set(_rules(client, estimate))
    assert deck_only < both
    assert any(k.startswith("pier_") for k in both - deck_only)


# -------------------------------------------------------------- the ladder


def test_every_row_reports_the_whole_ladder(client, db, estimate):
    """
    The card's real job. A rate you cannot trace is a rate you cannot defend
    three months later, and this app has spent its whole life finding numbers
    nobody could explain.
    """
    _build(db, estimate, "deck_fixture")
    row = _rules(client, estimate)["waste_concrete"]
    for field in (
        "value", "source", "job_value", "assembly_values",
        "company_value", "default_value", "read_by", "overridden_by",
    ):
        assert field in row, f"{field} dropped on the way out"


def test_assembly_values_are_reported_per_kind(client, db, estimate):
    """
    `assembly_rates` is keyed by KIND, so on a job with a deck AND piers the
    same key can have two different assembly answers. Flattening them to one
    number would print a figure that is wrong for one of the two sections.
    """
    _build(db, estimate, "deck_fixture")
    _build(db, estimate, "piers_fixture")
    rows = _rules(client, estimate)
    multi = [r for r in rows.values() if len(r["assembly_values"]) > 1]
    assert multi, "deck + piers is expected to share at least one assembly rate"
    for r in multi:
        assert set(r["assembly_values"]) <= {"cip_deck", "piers"}


def test_a_job_rule_beats_the_assembly_and_the_company(client, db, estimate):
    section = _build(db, estimate, "deck_fixture")
    r = client.put(
        f"/api/estimates/{estimate.id}/rules/waste_concrete",
        json={"value": "0.09", "note": "long pumps on this one"},
    )
    assert r.status_code == 200, r.text

    row = _rules(client, estimate)["waste_concrete"]
    assert D(str(row["value"])) == D("0.09")
    assert row["source"] == "job"
    assert row["note"] == "long pumps on this one"


def test_setting_a_rule_rewrites_the_job(client, db, estimate):
    """
    A rule is read live, which is exactly why it cannot wait for a later
    recalc: every stored calc_* column was computed under the OLD rule, so
    until something rewrites them the job shows one number while the rule says
    another. sql/053 shipped a company key that rewrote nothing and reported
    success — the same failure one layer up.
    """
    section = _build(db, estimate, "deck_fixture")
    before = _cost(db, section.id)
    # Form rental shoring is 32,100 SF at $1.25 — $44,138 on LBJ — so doubling
    # its multiplier is a number you can see from across the room.
    client.put(
        f"/api/estimates/{estimate.id}/rules/form_rental_shoring_multiplier",
        json={"value": "2"},
    )
    assert _cost(db, section.id) > before


def test_clearing_a_rule_puts_it_back(client, db, estimate):
    """
    An emptied rule is "stop overriding", not zero — there is no unset row, so
    clearing DELETES it. And the job has to come back to the number it had, or
    the override was destructive.
    """
    section = _build(db, estimate, "deck_fixture")
    before = _cost(db, section.id)
    client.put(
        f"/api/estimates/{estimate.id}/rules/form_rental_shoring_multiplier",
        json={"value": "2"},
    )
    assert _cost(db, section.id) != before
    r = client.delete(
        f"/api/estimates/{estimate.id}/rules/form_rental_shoring_multiplier"
    )
    assert r.status_code == 200, r.text

    rows = _rules(client, estimate)
    assert rows["form_rental_shoring_multiplier"]["job_value"] is None
    assert _cost(db, section.id) == before
    left = db.execute(
        text("SELECT count(*) FROM estimate_rules WHERE estimate_id = :e"),
        {"e": str(estimate.id)},
    ).scalar()
    assert left == 0


# ---------------------------------------------- who is not listening, and why


def test_a_section_rate_is_reported_as_not_listening(client, db, estimate):
    """
    `section_rates` beats the job. Setting a job rule that a section overrides
    is not an error — it is the normal case — but the card has to say the job
    number is not what that section prices at.
    """
    section = _build(db, estimate, "deck_fixture")
    client.put(
        f"/api/sections/{section.id}/rates/reshoring_multiplier", json={"value": "1.4"}
    )
    client.put(
        f"/api/estimates/{estimate.id}/rules/reshoring_multiplier", json={"value": "1.1"}
    )

    row = _rules(client, estimate)["reshoring_multiplier"]
    assert D(str(row["value"])) == D("1.1")
    assert [s["name"] for s in row["overridden_by"]] == [section.name]
    assert row["overridden_by"][0]["source"] == "section"
    assert D(str(row["overridden_by"][0]["value"])) == D("1.4")


def test_the_four_column_rules_are_flagged(client, db, estimate):
    """
    waste concrete/sand/rebar and form % are columns on `estimate_sections`,
    read by `calc._waste` BEFORE the ladder runs. The row says so, because a
    job rule that silently does nothing on half the sections is exactly the
    class of bug this app keeps finding in the workbook.
    """
    _build(db, estimate, "deck_fixture")
    rows = _rules(client, estimate)
    for key in ("waste_concrete", "waste_sand", "waste_rebar", "form_percent"):
        if key in rows:
            assert rows[key]["is_section_column"] is True
    assert rows["reshoring_multiplier"]["is_section_column"] is False


def test_a_section_column_is_reported_and_wins(client, db, estimate):
    """
    The column beats even a section rate, so it is what gets named. Typing a
    job waste and watching the section not move is the moment the screen has to
    explain itself.
    """
    section = _build(db, estimate, "deck_fixture")
    section.waste_concrete = D("0.07")
    db.flush()
    client.put(
        f"/api/estimates/{estimate.id}/rules/waste_concrete", json={"value": "0.15"}
    )

    row = _rules(client, estimate)["waste_concrete"]
    assert D(str(row["value"])) == D("0.15"), "the job still says what it says"
    assert len(row["overridden_by"]) == 1
    assert row["overridden_by"][0]["source"] == "column"
    assert D(str(row["overridden_by"][0]["value"])) == D("0.07")


def test_a_section_that_agrees_is_not_listed_as_overriding(client, db, estimate):
    """`overridden_by` is who is NOT listening, not a roster of sections."""
    _build(db, estimate, "deck_fixture")
    client.put(
        f"/api/estimates/{estimate.id}/rules/reshoring_multiplier", json={"value": "1.1"}
    )
    assert _rules(client, estimate)["reshoring_multiplier"]["overridden_by"] == []


# --------------------------------------------------------------- refusals


def test_a_price_is_refused_with_somewhere_to_go(client, db, estimate):
    """
    `_rate_numeric` never consults estimate_rules for a monetary key, so a row
    written here would sit in the table looking like a decision and change
    nothing at all. Worse than no box — so it 400s, and says where the price
    lives instead.
    """
    _build(db, estimate, "deck_fixture")
    r = client.put(
        f"/api/estimates/{estimate.id}/rules/labor_place_finish_sf",
        json={"value": "0.42"},
    )
    assert r.status_code == 400
    assert "price sheet" in r.json()["detail"]
    assert "Place & finish" in r.json()["detail"]


def test_an_unknown_key_is_refused(client, db, estimate):
    _build(db, estimate, "deck_fixture")
    r = client.put(
        f"/api/estimates/{estimate.id}/rules/not_a_rule", json={"value": "1"}
    )
    assert r.status_code == 400
    assert "RULE_KEYS" in r.json()["detail"]


def test_an_unknown_estimate_404s(client, db):
    import uuid

    r = client.get(f"/api/estimates/{uuid.uuid4()}/rules")
    assert r.status_code == 404


def test_every_field_the_card_reads_is_served(client, db, estimate):
    """
    The schema-drop guard, for the seventh time. `perm_edge_lf`, `gb_form_ff`,
    `pt_lb`, `subcontracted`, `labor_subcontracted` and `enabled` all reached
    the model and not the schema, and each one rendered as a dash or a
    permanently-checked box with the server quietly disagreeing.

    Every name below is read by `renderEstimateRulesCard` /
    `estimateRuleRowHtml` in app.js. Dropping one does not fail — it renders
    wrong, forever.
    """
    section = _build(db, estimate, "deck_fixture")
    section.waste_concrete = D("0.07")
    db.flush()
    client.put(
        f"/api/estimates/{estimate.id}/rules/form_rental_shoring_multiplier",
        json={"value": "1.4", "note": "steel prices"},
    )

    body = client.get(f"/api/estimates/{estimate.id}/rules").json()
    for field in ("estimate_id", "name", "rows", "set_here", "section_count"):
        assert field in body, field

    rows = {r["key"]: r for r in body["rows"]}
    for r in rows.values():
        for field in (
            "key", "label", "unit", "description", "group", "group_order",
            "value", "source", "job_value", "note", "assembly_values",
            "company_value", "default_value", "is_section_column",
            "read_by", "overridden_by",
        ):
            assert field in r, f"{field} dropped from {r.get('key')}"

    # The grouping the card sorts by has to be real, not every row in "Other".
    assert len({r["group"] for r in rows.values()}) > 1
    assert all(isinstance(r["group_order"], int) for r in rows.values())

    off = rows["waste_concrete"]["overridden_by"]
    assert off, "the section column has to reach the screen"
    for field in ("section_id", "name", "kind", "value", "source"):
        assert field in off[0], field


def test_a_job_with_no_sections_does_not_explode(client, db, estimate):
    """
    A brand-new job. The card should come back empty rather than 500 — there
    is nothing reading a rule yet, which is a true and unremarkable answer.
    """
    r = client.get(f"/api/estimates/{estimate.id}/rules")
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == []
    assert r.json()["section_count"] == 0


def test_the_table_still_ships_empty_for_untouched_jobs(client, db, estimate):
    """
    The proof this change moves nothing: reading the card writes no rows, so a
    job nobody has edited prices exactly as it did before the screen existed.
    """
    section = _build(db, estimate, "deck_fixture")
    before = _cost(db, section.id)
    _rules(client, estimate)
    assert (
        db.execute(
            text("SELECT count(*) FROM estimate_rules WHERE estimate_id = :e"),
            {"e": str(estimate.id)},
        ).scalar()
        == 0
    )
    assert _cost(db, section.id) == before
