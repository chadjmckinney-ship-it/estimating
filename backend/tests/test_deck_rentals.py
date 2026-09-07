"""
The elevated deck's rentals — forms, shoring, reshoring — as their own card,
with a quote of their own (sql/071, 2026-09-07).

Chad: "think we need to rework CIP elevated... giving it a separate section
from materials for form rentals, shoring and reshoring" — "we usually rent
forming materials and shoring for a project.. so allowing a quote works" —
"$0.5 forms, $0.75 shoring and reshoring".

Three lines in a rentals group of the forming line set, each deck SF times
its own $/SF times its own 1.10; the materials card no longer carries them;
a "shoring" quote on a deck section replaces all three; the catalog figure
beside that quote is what the three would have cost.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services.forming import RENTAL_CODES, load_stored_forming, refresh_and_store_forming
from app.services.recalc import recalc_section
from tests import deck_fixture as df
from tests import mono_slab_fixture as mf

D = Decimal
SF = D("32100")
TAX = D("1.0825")  # the fixture's sales_tax_pct, as test_cip_deck reads it


def _cost(db, section_id) -> Decimal:
    return D(str(db.scalar(text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"), {"i": str(section_id)})))


def _build(db, estimate):
    section = df.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    recalc_section(db, section)
    db.flush()
    return section


def _lines(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, section_id)["lines"]}


def test_three_lines_in_their_own_group_at_chads_numbers(db, estimate):
    section = _build(db, estimate)
    payload = load_stored_forming(db, section.id)
    ln = {x["code"]: x for x in payload["lines"]}
    for code, rate in (("form_rental", "0.50"), ("shoring_rental", "0.75"), ("reshoring", "0.75")):
        assert ln[code]["group"] == "rentals", code
        assert D(str(ln[code]["qty"])) == SF and D(str(ln[code]["unit_cost"])) == D(rate), code
        assert D(str(ln[code]["ext_cost"])) == (SF * D(rate) * D("1.1")).quantize(D("0.01")), code
        assert ln[code]["missing_price"] is False and ln[code]["taxable"] is True
    assert "form_rental_shoring" not in ln, "the combined line retired"
    materials = [x for x in payload["lines"] if x["group"] != "rentals"]
    assert materials and all(x["code"] not in RENTAL_CODES for x in materials)
    assert D(str(payload["rentals_ext_cost"])) == D("70620.00")  # 17,655 + 26,482.50 + 26,482.50
    assert D(str(payload["rentals_ext_cost"])) + D(str(payload["materials_ext_cost"])) == D(str(payload["total_ext_cost"]))


def test_each_allowance_is_its_own_rule(db, estimate):
    section = _build(db, estimate)
    before = _lines(db, section.id)
    db.execute(text("UPDATE assembly_rates SET value = 1.5 WHERE kind = 'cip_deck' AND key = 'forms_multiplier'"))
    db.flush()
    refresh_and_store_forming(db, section.id)
    after = _lines(db, section.id)
    assert D(str(after["form_rental"]["ext_cost"])) == (SF * D("0.50") * D("1.5")).quantize(D("0.01"))
    for code in ("shoring_rental", "reshoring"):
        assert after[code]["ext_cost"] == before[code]["ext_cost"], code


def test_a_shoring_quote_replaces_all_three_and_clearing_it_brings_them_back(client, db, estimate):
    section = _build(db, estimate)
    before = _cost(db, section.id)
    r = client.get(f"/api/sections/{section.id}")
    assert "shoring" in r.json()["quote_kinds"], r.json().get("quote_kinds")

    r = client.put(f"/api/sections/{section.id}/quotes/shoring",
                   json={"amount": "60000", "unit": "LS", "note": "Ace Shoring, per the job"})
    assert r.status_code == 200, r.text
    q = next(x for x in r.json() if x["kind"] == "shoring")
    assert D(str(q["quoted_total"])) == D("60000.00")
    assert D(str(q["catalog_total"])) == D("70620.00"), "what the three lines would have cost"
    assert q["catalog_verdict"] == "ok"

    ln = _lines(db, section.id)
    assert set(ln) & RENTAL_CODES == {"shoring_quote"}, sorted(set(ln) & RENTAL_CODES)
    assert D(str(ln["shoring_quote"]["ext_cost"])) == D("60000.00") and ln["shoring_quote"]["group"] == "rentals"
    assert ln["shoring_quote"]["taxable"] is True
    after = _cost(db, section.id)
    # Tax is applied per line and rounded there; the difference of two rounded
    # totals can sit a cent from the rounded difference.
    assert abs((before - after) - (D("70620.00") - D("60000.00")) * TAX) <= D("0.01")

    r = client.delete(f"/api/sections/{section.id}/quotes/shoring")
    assert r.status_code == 200, r.text
    ln = _lines(db, section.id)
    assert {"form_rental", "shoring_rental", "reshoring"} <= set(ln) and "shoring_quote" not in ln
    assert _cost(db, section.id) == before


def test_a_per_sf_quote_prices_the_deck_area(client, db, estimate):
    section = _build(db, estimate)
    r = client.put(f"/api/sections/{section.id}/quotes/shoring", json={"amount": "2.00", "unit": "SF"})
    assert r.status_code == 200, r.text
    ln = _lines(db, section.id)
    assert D(str(ln["shoring_quote"]["ext_cost"])) == SF * D("2.00")
    assert D(str(ln["shoring_quote"]["qty"])) == SF


def test_only_a_deck_carries_the_quote(client, db, estimate):
    slab = mf.build(db, estimate)
    r = client.put(f"/api/sections/{slab.id}/quotes/shoring", json={"amount": "1000", "unit": "LS"})
    assert r.status_code == 400 and "cannot carry" in r.json()["detail"], r.text
    assert "shoring" not in client.get(f"/api/sections/{slab.id}").json()["quote_kinds"]


def test_a_missing_rental_price_is_reported_as_a_rental(db, estimate):
    section = _build(db, estimate)
    db.execute(text("DELETE FROM estimate_prices WHERE estimate_id = :e AND ref_key = 'shoring_rental_sf'"),
               {"e": str(estimate.id)})
    db.flush()
    recalc_section(db, section)
    db.flush()
    ln = _lines(db, section.id)
    assert ln["shoring_rental"]["missing_price"] is True
    unpriced = db.scalar(text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"), {"i": str(section.id)})
    assert any("SHORING RENTAL" in x and "rentals" in x for x in unpriced), unpriced
