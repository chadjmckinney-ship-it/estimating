"""
Every write model refuses a field it does not know, and every payload a
screen sends is one it knows. (audit 2026-09-04: P2 #6, #7, #8)

## #8 — `extra="forbid"` everywhere money is written

"A bulk save silently swallowed misspelled pier fields and returned zero
rebar with a 200 OK" is the sentence pasted into the wall, column, deck and
quote schemas to explain their `extra="forbid"`. The two assemblies it
actually happened on — piers, and the mono slab that carries the paving grid
— never got it, and neither did beam types, grade beams, the estimate, the
project, the two line PATCHes, the three catalogs, the settings or the
rules. A renamed field in app.js on any of those was a 200 that changed
nothing. The first half of this file is that matrix, closed.

The second half is the guard the first half needs: `forbid` on a schema
that the screen sends an unknown field to is a screen that stops working
with a 422. So every payload shape app.js builds — each modal, each grid
row, each line PATCH — is sent here exactly as the screen builds it, and
has to be accepted. Renaming a field on either side breaks this file before
it breaks Chad's screen.

## #6 — the estimate modal's dead waste inputs

`waste_concrete`, `waste_sand` and `waste_rebar` left `estimates` in sql/034
and have lived on the section and in the rules ladder since. The modal kept
three boxes for them and sent them on every save; `EstimateUpdate` still
declared one; the router setattr'd it onto an ORM row with no such column.
Accepted, discarded, and the modal reopened blank. The boxes are gone and
the fields are refused.

## #7 — project tax exemption had no screen and no consequence

`projects.tax_exempt` is the flag every section follows unless it says
otherwise, and it moves 8.25% of every material and rental dollar. The
project modal never offered it, POST dropped it on the floor, and PATCH
accepted it and recalculated nothing — so a job flipped to exempt kept every
stored `calc_tax` until something else happened to recalc. Now it is on the
form, stored on create, and a flip re-costs the job's open estimates on the
spot; final and archived ones keep their bid numbers.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.costing import refresh_pour_costs
from tests import mono_slab_fixture as mf
from tests import piers_fixture as pf

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def slab(db, estimate):
    section = mf.build(db, estimate)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def _pour_id(db, section_id) -> str:
    return str(db.execute(
        text("SELECT id FROM mono_slabs WHERE section_id = :s ORDER BY created_at LIMIT 1"),
        {"s": str(section_id)},
    ).scalar())


def _mix_id(db) -> int:
    return int(db.execute(
        text("SELECT id FROM mix_designs WHERE is_active ORDER BY id LIMIT 1")
    ).scalar())


def _beam_type_id(client, section_id) -> str:
    types = client.get(f"/api/sections/{section_id}/beam-types").json()
    assert types, "the slab fixture carries a beam schedule"
    return types[0]["id"]


def _section_tax(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_tax FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _section_cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _estimate_cost(db, estimate_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimates WHERE id = :i"),
        {"i": str(estimate_id)},
    ).scalar()


# ------------------------------------------------- #8: a typo is a 422 ----


def test_the_pier_grid_refuses_a_misspelled_field(client, db, estimate):
    """The one it happened on. `vert_bars_szie` used to be a 200 and no bar."""
    section = pf.build(db, estimate)
    r = client.put(
        "/api/pier-groups/bulk",
        json={"section_id": str(section.id),
              "rows": [{"qty": 4, "diameter_in": 24, "vert_bars_szie": 8}]},
    )
    assert r.status_code == 422, r.text


def test_the_paving_grid_refuses_a_misspelled_field(client, db, slab):
    """Twenty-five areas across sixteen columns — the biggest bulk save in the app."""
    r = client.put(
        "/api/mono-slabs/bulk",
        json={"section_id": str(slab.id),
              "rows": [{"square_footage": 1000, "thickness_in": 5, "curb_lff": 10}]},
    )
    assert r.status_code == 422, r.text


def test_every_other_write_model_refuses_one_too(client, db, project, estimate, slab):
    pour = _pour_id(db, slab.id)
    bt = _beam_type_id(client, slab.id)
    client.get(f"/api/sections/{slab.id}/labor")        # stores the line sets
    client.get(f"/api/sections/{slab.id}/equipment")
    mix = _mix_id(db)
    mat = client.get("/api/materials").json()[0]["id"]
    eq = client.get("/api/equipment").json()[0]["id"]

    cases = [
        ("POST", "/api/mono-slabs",
         {"section_id": str(slab.id), "square_footage": 100, "thickness_in": 4, "thickness_inn": 4}),
        ("PATCH", f"/api/mono-slabs/{pour}", {"square_footage": 100, "sqaure_footage": 100}),
        ("POST", "/api/pier-groups",
         {"section_id": str(slab.id), "qty": 1, "diameter_in": 24, "diameter_inn": 24}),
        ("POST", f"/api/sections/{slab.id}/beam-types",
         {"label": "X", "width_in": 12, "height_in": 24, "stirrup_szie": 3}),
        ("PATCH", f"/api/beam-types/{bt}", {"stirrup_szie": 3}),
        ("POST", "/api/grade-beams",
         {"mono_slab_id": pour, "beam_type_id": bt, "length_lf": 10, "lenght_lf": 10}),
        ("PUT", f"/api/mono-slabs/{pour}/grade-beams",
         {"kind": "grade_beam", "beams": [{"beam_type_id": bt, "length_lf": 10, "notes2": ""}]}),
        ("POST", "/api/estimates",
         {"project_id": str(project.id), "name": "typo", "waste_concrete": 0.05}),
        ("PATCH", f"/api/estimates/{estimate.id}", {"nmae": "x"}),
        ("POST", "/api/projects", {"name": "typo", "tax_exmpt": True}),
        ("PATCH", f"/api/projects/{project.id}", {"tax_exmpt": True}),
        ("PATCH", f"/api/materials/{mat}", {"unit_cots": 1}),
        ("POST", "/api/materials", {"name": "x", "category": "y", "unit": "EA", "unit_cots": 1}),
        ("PATCH", f"/api/equipment/{eq}", {"unit_cots": 1}),
        ("POST", "/api/equipment", {"name": "x", "unit_cots": 1}),
        ("PATCH", f"/api/mix-designs/{mix}", {"unit_cots": 1}),
        ("POST", "/api/mix-designs", {"code": "x", "name": "x", "unit_cots": 1}),
        ("PATCH", f"/api/sections/{slab.id}/labor/lines/superintendent", {"qyt": 1}),
        ("PATCH", f"/api/sections/{slab.id}/equipment/lines/skid_steer", {"day_qty": 1}),
        ("PATCH", "/api/system-settings/waste_concrete", {"vlaue": "0.05"}),
        ("PUT", f"/api/estimates/{estimate.id}/rules/waste_concrete", {"valeu": "0.05"}),
    ]
    wrong = []
    for method, url, body in cases:
        r = client.request(method, url, json=body)
        if r.status_code != 422:
            wrong.append((method, url, r.status_code))
    assert wrong == [], f"a misspelled field was not refused: {wrong}"


# --------------------------------------------- #6: the waste inputs are gone


def test_the_estimate_no_longer_takes_a_waste_factor(client, db, estimate):
    """
    What the modal sent for a week. The field is neither a column nor a
    default any more; accepting it and dropping it was the bug.
    """
    for body in ({"waste_concrete": 0.07}, {"waste_sand": 0.05},
                 {"waste_rebar": 0.1}, {"form_percent": 0.5}):
        r = client.patch(f"/api/estimates/{estimate.id}", json=body)
        assert r.status_code == 422, (body, r.text)


# ------------------------------------------ #8: what the screens send lands


def test_every_payload_the_screens_build_is_accepted(client, db, project, estimate, slab):
    """
    Each body below is the shape app.js builds — modal by modal, grid by
    grid — so `forbid` on the server and a rename on the screen meet here
    first. A 422 in this test is a screen that stopped saving.
    """
    tag = uuid.uuid4().hex[:6]
    mix = _mix_id(db)
    pour = _pour_id(db, slab.id)
    piers = pf.build(db, estimate)
    client.get(f"/api/sections/{slab.id}/labor")
    client.get(f"/api/sections/{slab.id}/equipment")

    # openProjectModal
    r = client.post("/api/projects", json={
        "name": f"Screen {tag}", "gc": "OHT", "location": "Dallas", "job_number": "26-999",
        "status": "not_started", "bid_due": "2026-10-01", "tax_exempt": False,
        "project_types": ["Retail"], "created_by": None,
        "plans_url": "https://example.test/plans", "notes": None,
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={
        "name": f"Screen {tag}", "gc": "OHT", "location": "Dallas", "job_number": "26-999",
        "status": "in_progress", "bid_due": "2026-10-01", "tax_exempt": True,
        "project_types": ["Retail"], "created_by": None, "plans_url": None, "notes": "n",
    })
    assert r.status_code == 200, r.text

    # openEstimateModal
    r = client.post("/api/estimates", json={
        "project_id": str(project.id), "name": f"Est {tag}", "version": 1,
        "status": "draft", "estimator_id": None, "margin_pct": 0.2,
        "contingency_pct": 0.03, "notes": None,
    })
    assert r.status_code == 201, r.text
    r = client.patch(f"/api/estimates/{r.json()['id']}", json={
        "name": f"Est {tag}", "version": 2, "status": "in_review", "estimator_id": None,
        "margin_pct": 0.18, "contingency_pct": 0, "notes": "n",
    })
    assert r.status_code == 200, r.text

    # openMonoSlabModal — create, then edit
    slab_body = {
        "description": "Pour Z", "location": None, "square_footage": 1000,
        "thickness_in": 4, "sand_thickness_in": 2, "perimeter_edge_lf": 100,
        "mix_design_id": mix, "post_tension": True, "wire_mesh": False,
        "slab_bar_size": 4, "slab_bar_spacing_in": 18, "support_rebar_lb_per_sf": None,
        "pt_lb_per_sf": None, "pt_spacing_in": 48, "notes": None,
    }
    r = client.post("/api/mono-slabs", json={**slab_body, "section_id": str(slab.id)})
    assert r.status_code == 201, r.text
    r = client.patch(f"/api/mono-slabs/{r.json()['id']}", json=slab_body)
    assert r.status_code == 200, r.text

    # pavingColumns → wireGrid → bulkSaveMonoSlabs
    r = client.put("/api/mono-slabs/bulk", json={"section_id": str(slab.id), "rows": [{
        "description": "Light Duty", "square_footage": 1000, "thickness_in": 5,
        "curb_lf": 50, "thick_edge_lf": None, "mix_design_id": mix,
        "sand_thickness_in": 2, "slab_bar_size": 3, "slab_bar_spacing_in": 18,
        "mesh_gauge": None, "demo_lf": None, "paving_add_per_sf": None,
        "slip_form": False, "traffic_control": False,
    }]})
    assert r.status_code == 200, r.text

    # pierColumns → wireGrid → bulkSavePierGroups
    r = client.put("/api/pier-groups/bulk", json={"section_id": str(piers.id), "rows": [{
        "label": "G", "qty": 4, "diameter_in": 24, "base_depth_ft": 16,
        "rock_penetration_ft": 3, "bell_size_in": None, "mix_design_id": mix,
        "vert_bars_count": 7, "vert_bars_size": 6, "tie_size": 3, "tie_spacing_in": 10,
        "band_tie_count": 3, "band_spacing_in": 3, "dowels_count": 4, "dowels_size": 6,
        "dowels_length_ft": 8,
    }]})
    assert r.status_code == 200, r.text

    # openBeamTypeModal — create; openGradeBeamsModal.saveTypes — edit
    r = client.post(f"/api/sections/{slab.id}/beam-types", json={
        "label": f"GB {tag}", "kind": "grade_beam", "width_in": 12, "height_in": 24,
        "top_bars_count": 2, "top_bars_size": 5, "bottom_bars_count": 2, "bottom_bars_size": 5,
        "mid_bars_count": None, "mid_bars_size": None, "stirrup_size": 3,
        "stirrup_spacing_in": 18, "form_face_in": None, "pt_cables_count": 2, "notes": None,
    })
    assert r.status_code == 201, r.text
    bt = r.json()["id"]
    r = client.patch(f"/api/beam-types/{bt}", json={
        "kind": "grade_beam", "label": f"GB {tag}", "width_in": 12, "height_in": 30,
        "top_bars_count": 2, "top_bars_size": 5, "bottom_bars_count": 2, "bottom_bars_size": 5,
        "mid_bars_count": None, "mid_bars_size": None, "stirrup_size": 3,
        "stirrup_spacing_in": 18, "pt_cables_count": 2,
    })
    assert r.status_code == 200, r.text

    # openGradeBeamsModal.saveUsages — replaceGradeBeams
    r = client.put(f"/api/mono-slabs/{pour}/grade-beams", json={
        "kind": "grade_beam", "beams": [{"beam_type_id": bt, "length_lf": 100}],
    })
    assert r.status_code == 200, r.text

    # renderLaborCard: Save, and the On/Off checkbox
    r = client.patch(f"/api/sections/{slab.id}/labor/lines/superintendent",
                     json={"enabled": True, "mark_manual": True, "rate": 425, "qty": 10})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/sections/{slab.id}/labor/lines/superintendent",
                     json={"enabled": False, "mark_manual": None})
    assert r.status_code == 200, r.text

    # renderEquipmentCard: Save, and the checkbox
    r = client.patch(f"/api/sections/{slab.id}/equipment/lines/skid_steer",
                     json={"enabled": True, "mark_manual": True, "rate": 225, "days_qty": 9})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/sections/{slab.id}/equipment/lines/skid_steer",
                     json={"enabled": True, "mark_manual": False})
    assert r.status_code == 200, r.text

    # renderMaterials / renderEquipment / renderMixes — create, edit, reactivate
    r = client.post("/api/materials", json={
        "name": f"WIDGET {tag}", "category": "lumber", "unit": "EA", "unit_cost": 1.25,
        "unit_note": None, "code": None, "supplier_ref": None,
        "price_as_of": "2026-09-04", "description": None,
    })
    assert r.status_code == 201, r.text
    mat = r.json()["id"]
    assert client.patch(f"/api/materials/{mat}", json={"is_active": True}).status_code == 200
    r = client.post("/api/equipment", json={
        "name": f"WIDGET LIFT {tag}", "category": "other", "unit": "DAY", "unit_cost": 100,
        "unit_note": None, "code": f"WL-{tag}", "price_as_of": None,
        "is_owned": False, "description": None,
    })
    assert r.status_code == 201, r.text
    assert client.patch(f"/api/equipment/{r.json()['id']}", json={"is_active": True}).status_code == 200
    r = client.post("/api/mix-designs", json={
        "code": f"T-{tag}", "name": f"Test mix {tag}", "strength_psi": 3000,
        "unit_cost": 150, "has_ash": False, "has_air": False, "notes": None,
    })
    assert r.status_code == 201, r.text
    assert client.patch(f"/api/mix-designs/{r.json()['id']}", json={
        "code": f"T-{tag}", "name": f"Test mix {tag}", "strength_psi": 3000,
        "unit_cost": 155, "has_ash": True, "has_air": False, "notes": "n",
    }).status_code == 200

    # wireEstimateRules / wireSectionRates / wireSettings
    assert client.put(f"/api/estimates/{estimate.id}/rules/waste_concrete",
                      json={"value": "0.09", "note": "long pumps"}).status_code == 200
    assert client.put(f"/api/sections/{slab.id}/rates/labor_forming_sf",
                      json={"value": "0.42", "note": "Ramirez"}).status_code == 200
    assert client.patch("/api/system-settings/waste_concrete",
                        json={"value": "0.05"}).status_code == 200


# ------------------------------------------------ #7: the project's tax ----


def test_a_project_created_exempt_is_stored_exempt(client, db):
    r = client.post("/api/projects", json={"name": "ROW job", "tax_exempt": True})
    assert r.status_code == 201, r.text
    assert r.json()["tax_exempt"] is True
    assert client.get(f"/api/projects/{r.json()['id']}").json()["tax_exempt"] is True


def test_flipping_the_projects_tax_reprices_its_open_estimates(client, db, project, estimate, slab):
    """
    The bug. A section that says nothing about tax inherits the project's
    flag at cost time, so flipping the flag used to change nothing stored.
    """
    assert slab.tax_exempt is None, "the fixture section follows the project"
    tax_before = _section_tax(db, slab.id)
    cost_before = _section_cost(db, slab.id)
    assert tax_before > 0

    r = client.patch(f"/api/projects/{project.id}", json={"tax_exempt": True})
    assert r.status_code == 200, r.text
    assert r.json()["tax_exempt"] is True

    db.expire_all()
    assert _section_tax(db, slab.id) == D("0.00")
    assert _section_cost(db, slab.id) == cost_before - tax_before
    assert _estimate_cost(db, estimate.id) == _section_cost(db, slab.id), "the job followed"

    # ...and back, because a flag is not a one-way door.
    client.patch(f"/api/projects/{project.id}", json={"tax_exempt": False})
    db.expire_all()
    assert _section_tax(db, slab.id) == tax_before


def test_a_section_with_its_own_answer_does_not_follow(client, db, project, estimate, slab):
    """`false` on the section is a decision, not blank — it stays taxed."""
    slab.tax_exempt = False
    db.flush()
    refresh_pour_costs(db, slab)
    db.flush()
    tax_before = _section_tax(db, slab.id)
    assert tax_before > 0

    client.patch(f"/api/projects/{project.id}", json={"tax_exempt": True})
    db.expire_all()
    assert _section_tax(db, slab.id) == tax_before


def test_a_frozen_estimate_keeps_its_bid_numbers(client, db, project, estimate, slab):
    """
    Same line the company sweep will not cross. A final bid went out with
    tax; repricing it is its own Recalculate button, deliberately.
    """
    from app.services.recalc import recalc_estimate

    db.execute(text("UPDATE estimates SET status = 'final' WHERE id = :i"), {"i": str(estimate.id)})
    db.commit()
    tax_before = _section_tax(db, slab.id)
    assert tax_before > 0

    r = client.patch(f"/api/projects/{project.id}", json={"tax_exempt": True})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert _section_tax(db, slab.id) == tax_before, "a final bid must not move"

    # The deliberate override still works.
    recalc_estimate(db, estimate)
    db.expire_all()
    assert _section_tax(db, slab.id) == D("0.00")


def test_a_save_that_does_not_touch_tax_reprices_nothing(client, db, project, estimate, slab):
    """A rename is a rename. Only a flipped flag re-costs the job."""
    from app.models.estimate_section import EstimateSection

    stamp = db.execute(
        text("SELECT updated_at FROM estimate_sections WHERE id = :i"), {"i": str(slab.id)}
    ).scalar()
    r = client.patch(f"/api/projects/{project.id}", json={"name": "Renamed", "tax_exempt": False})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(EstimateSection, slab.id).updated_at == stamp
