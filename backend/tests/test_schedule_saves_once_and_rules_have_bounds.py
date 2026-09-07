"""
The frontend list and the oddments (audit 2026-09-04, P3 — batch 3, 2026-09-06).

The grade-beams modal saved its schedule one PATCH at a time (five recalcs for
five types, and a failure on the third left two saved); a rule on the ladder
had no bounds where the section columns have CHECKs; a plans link went into an
href as whatever was typed; the rental-tier switch was read raw around the
ladder, so a job rule for it was shown and ignored; a pull refreshed a row's
label but not its unit; the paving siding line's formula text said `× form%`
after the quantity stopped scaling by it; ColumnType never stamped updated_at.
The `beforeunload` leak and the three labels are the Playwright spec's.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.column_type import ColumnType
from app.models.estimate_price import EstimatePrice
from app.models.material import Material
from app.services.estimate_equipment import rental_billable_units
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.price_book import pull_prices
from tests import mono_slab_fixture as mf
from tests import paving_fixture as pf
from tests import walls_fixture as wf

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ------------------------------------------------------ the schedule --


def _modal_row(t: dict | None, **over) -> dict:
    """The payload shape openGradeBeamsModal.saveTypes builds, per row."""
    base = {
        "id": None, "kind": "grade_beam", "label": "GB new", "width_in": 12, "height_in": 24,
        "top_bars_count": 2, "top_bars_size": 5, "bottom_bars_count": 2, "bottom_bars_size": 5,
        "mid_bars_count": None, "mid_bars_size": None, "stirrup_size": 3,
        "stirrup_spacing_in": 18, "pt_cables_count": None,
    }
    if t is not None:
        base = {k: t.get(k) for k in base}
    base.update(over)
    return base


def _types(client, section_id):
    return client.get(f"/api/sections/{section_id}/beam-types?kind=grade_beam").json()


def test_the_schedule_saves_in_one_request_with_one_recalc(client, db, estimate, monkeypatch):
    section = mf.build(db, estimate)
    before = _types(client, section.id)
    assert len(before) >= 2, "the slab fixture carries a beam schedule"

    import app.routers.beam_types as bt

    real, calls = bt._recalc_section, []

    def counted(db_, section_id):
        calls.append(section_id)
        real(db_, section_id)

    monkeypatch.setattr(bt, "_recalc_section", counted)
    rows = [_modal_row(t, height_in=str(D(t["height_in"]) + 6)) for t in before[:2]]
    rows.append(_modal_row(None, label="GB brand new"))
    r = client.put(f"/api/sections/{section.id}/beam-types/bulk", json={"rows": rows})
    assert r.status_code == 200, r.text
    assert (r.json()["created"], r.json()["updated"]) == (1, 2)
    assert calls == [section.id]

    after = {t["id"]: t for t in _types(client, section.id)}
    assert any(t["label"] == "GB brand new" for t in after.values())
    for t in before[:2]:
        assert D(after[t["id"]]["height_in"]) == D(t["height_in"]) + 6
        if D(t["total_lf"]) > 0:  # a taller beam is more concrete on every pour using it
            assert D(after[t["id"]]["total_concrete_cy"]) > D(t["total_concrete_cy"])


def test_a_save_from_the_modal_keeps_what_the_type_editor_set(client, db, estimate):
    """The modal shows a subset of the fields; saving it must not blank the rest."""
    section = mf.build(db, estimate)
    t = _types(client, section.id)[0]
    r = client.patch(f"/api/beam-types/{t['id']}", json={"notes": "keep me", "l_bars_count": 4, "l_bars_size": 5})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/sections/{section.id}/beam-types/bulk", json={"rows": [_modal_row(t, width_in=14)]})
    assert r.status_code == 200, r.text
    after = next(x for x in r.json()["rows"] if x["id"] == t["id"])
    assert (after["width_in"], after["notes"], after["l_bars_count"]) == ("14", "keep me", 4) or (
        D(after["width_in"]) == 14 and after["notes"] == "keep me" and after["l_bars_count"] == 4
    )


def test_a_bad_row_saves_nothing_from_the_schedule(client, db, estimate):
    mine = mf.build(db, estimate)
    theirs = mf.build(db, estimate)
    a = _types(client, mine.id)[0]
    stray = _types(client, theirs.id)[0]
    rows = [_modal_row(a, height_in=str(D(a["height_in"]) + 6)), _modal_row(stray)]
    r = client.put(f"/api/sections/{mine.id}/beam-types/bulk", json={"rows": rows})
    assert r.status_code == 400 and "not on this section" in r.text, r.text
    db.expire_all()
    assert D(next(t for t in _types(client, mine.id) if t["id"] == a["id"])["height_in"]) == D(a["height_in"])


def test_a_misspelled_field_on_the_schedule_is_a_422(client, db, estimate):
    section = mf.build(db, estimate)
    rows = [_modal_row(None, stirrup_szie=3)]
    r = client.put(f"/api/sections/{section.id}/beam-types/bulk", json={"rows": rows})
    assert r.status_code == 422, r.text


# --------------------------------------------------------- rule bounds --


def test_a_rule_out_of_its_range_is_refused(client, estimate):
    def put(key, value):
        return client.put(f"/api/estimates/{estimate.id}/rules/{key}", json={"value": value})

    assert put("waste_concrete", "1.5").status_code == 400
    assert put("waste_concrete", "0.08").status_code == 200
    assert put("form_percent", "1.5").status_code == 200   # both faces (sql/057)
    assert put("form_percent", "2.5").status_code == 400
    assert put("haul_off_swell", "1.3").status_code == 200  # a multiplier, not a fraction
    assert put("equip_use_rental_tiers", "2").status_code == 400
    assert put("equip_use_rental_tiers", "0").status_code == 200
    assert put("waste_rebar", "-0.1").status_code == 422    # the schema's floor
    assert put("chairs_sf_per_bag", "5000000").status_code == 422  # the schema's ceiling


# ------------------------------------------------------------ plans_url --


def test_a_plans_link_must_be_a_web_address(client, project):
    r = client.patch(f"/api/projects/{project.id}", json={"plans_url": "javascript:alert(1)"})
    assert r.status_code == 422, r.text
    r = client.patch(f"/api/projects/{project.id}", json={"plans_url": "   "})
    assert r.status_code == 200 and r.json()["plans_url"] is None, r.text
    r = client.patch(f"/api/projects/{project.id}", json={"plans_url": " https://plans.test/lbj "})
    assert r.status_code == 200 and r.json()["plans_url"] == "https://plans.test/lbj", r.text


# -------------------------------------------------------- rental tiers --


def test_a_job_rule_can_turn_the_rental_tiers_off(client, db, estimate):
    section = wf.build(db, estimate)
    lines = client.get(f"/api/sections/{section.id}/equipment").json()["lines"]
    code = next(ln["code"] for ln in lines if ln["unit"] == "DAY")
    days = D("5")  # the first tier: four to seven days bill as three
    assert rental_billable_units(days, use_tiers=True) == D("3")

    def patch_days():
        r = client.patch(
            f"/api/sections/{section.id}/equipment/lines/{code}",
            json={"days_qty": str(days), "mark_manual": True},
        )
        assert r.status_code == 200, r.text
        return D(str(next(ln for ln in r.json()["lines"] if ln["code"] == code)["billable_units"]))

    def stored():
        lines = client.get(f"/api/sections/{section.id}/equipment").json()["lines"]
        return D(str(next(ln for ln in lines if ln["code"] == code)["billable_units"]))

    assert patch_days() == D("3")  # company default: tiers on

    r = client.put(f"/api/estimates/{estimate.id}/rules/equip_use_rental_tiers", json={"value": "0"})
    assert r.status_code == 200, r.text
    assert stored() == days, "the refresh path (a rule change recosts the job) reads the rule"
    assert patch_days() == days, "the line PATCH path reads the rule too"

    r = client.delete(f"/api/estimates/{estimate.id}/rules/equip_use_rental_tiers")
    assert r.status_code == 200, r.text
    assert stored() == D("3")
    assert patch_days() == D("3")


# ------------------------------------------------------------- the pull --


def test_a_pull_follows_the_masters_unit_and_category_too(db, estimate):
    mf.build(db, estimate)  # pulls a sheet
    row = db.scalars(
        select(EstimatePrice).where(
            EstimatePrice.estimate_id == estimate.id, EstimatePrice.kind == "material",
            EstimatePrice.is_edited.is_(False),
        )
    ).first()
    assert row is not None
    master = db.get(Material, row.ref_id)
    master.unit = "BOX"
    master.category = "steel" if master.category != "steel" else "lumber"  # the column has a CHECK
    wanted = master.category
    master.unit_cost = D(str(master.unit_cost)) + 1
    db.flush()
    result = pull_prices(db, estimate.id, apply=True)
    assert any(x["ref_id"] == row.ref_id for x in result.changed)
    db.flush()
    db.refresh(row)
    assert (row.unit, row.category) == ("BOX", wanted)
    assert D(str(row.value)) == D(str(master.unit_cost))


# ---------------------------------------------------------- the oddments --


def test_column_types_stamp_updated_at_on_update():
    assert ColumnType.__table__.c.updated_at.onupdate is not None


def test_the_paving_siding_formula_says_what_it_does(db, estimate):
    s = pf.build(db, estimate)
    refresh_and_store_forming(db, s.id)
    siding = next(ln for ln in load_stored_forming(db, s.id)["lines"] if ln["code"] == "siding")
    assert "form%" not in siding["formula"], siding["formula"]
