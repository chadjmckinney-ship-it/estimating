from decimal import Decimal
import pytest
from tests import walls_fixture as wf

@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.main import app
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_wall_endpoints(client, db, estimate):
    s = wf.build(db, estimate)
    r = client.get(f"/api/wall-runs?section_id={s.id}"); assert r.status_code == 200, r.text
    assert len(r.json()) == 16
    t = client.get(f"/api/wall-runs/totals?section_id={s.id}").json()
    assert Decimal(t["total_form_ff"]) == Decimal("3452.5500")
    # typo in a bulk row must 422, not silently drop
    bad = client.put("/api/wall-runs/bulk", json={"section_id": str(s.id),
        "rows": [{"length_ft": 10, "wall_height_in": 36, "ftg_widthin": 70}]})
    assert bad.status_code == 422, bad.text
    ok = client.put("/api/wall-runs/bulk", json={"section_id": str(s.id),
        "rows": [{"length_ft": 10, "wall_height_in": 36, "ftg_width_in": 70,
                  "ftg_thick_in": 12}], "delete_missing": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["deleted"] == 16 and ok.json()["created"] == 1


def test_footing_mix_is_writable_through_the_api(client, db, estimate):
    """
    The column existed, costing read it, and no schema carried it — so a create
    or PATCH setting it returned 200 and changed nothing. Exactly the sql/037
    shape, caught while importing LBJ's walls.
    """
    from decimal import Decimal

    r = client.post(
        f"/api/estimates/{estimate.id}/sections",
        json={"kind": "walls_footings", "name": "W", "unit": "FF",
              "footing_mix_design_id": 7},
    )
    assert r.status_code == 201, r.text
    assert r.json()["footing_mix_design_id"] == 7

    sid = r.json()["id"]
    p = client.patch(f"/api/sections/{sid}", json={"footing_mix_design_id": 3})
    assert p.status_code == 200, p.text
    assert p.json()["footing_mix_design_id"] == 3
    assert client.get(f"/api/sections/{sid}").json()["footing_mix_design_id"] == 3


def test_the_footing_mix_select_reprices_the_footings(client, db, estimate):
    """
    The "Footing mix" select on the walls page (2026-09-05 — Chad: "there is a
    field to chose mix designs for walls but not for the footing") sends
    exactly two shapes: {"footing_mix_design_id": <id>} and
    {"footing_mix_design_id": None}, the latter being "follows the wall's mix".
    The fixture's footing is 3500 @ $140 under a 4000 @ $145 wall, so clearing
    it must make every footing dearer on the spot, and setting it back must
    land on the same cents — the PATCH re-costs the runs, not just the flag.
    """
    s = wf.build(db, estimate)
    # wf.build stores the takeoff; the wall/footing split costs land on a
    # costing pass — the same one the page's Recalculate button runs.
    assert client.post(f"/api/sections/{s.id}/recalc").status_code == 200
    before = client.get(f"/api/sections/{s.id}").json()["footing_mix_design_id"]
    assert before is not None  # the sheet's R8
    rows = client.get(f"/api/wall-runs?section_id={s.id}").json()
    ftg_before = {r["id"]: Decimal(r["calc_footing_cost"]) for r in rows}
    assert len(ftg_before) == 16 and sum(ftg_before.values()) > 0

    p = client.patch(f"/api/sections/{s.id}", json={"footing_mix_design_id": None})
    assert p.status_code == 200, p.text
    assert p.json()["footing_mix_design_id"] is None
    for r in client.get(f"/api/wall-runs?section_id={s.id}").json():
        assert Decimal(r["calc_footing_cost"]) > ftg_before[r["id"]], r["label"]

    p = client.patch(f"/api/sections/{s.id}", json={"footing_mix_design_id": before})
    assert p.status_code == 200, p.text
    after = {r["id"]: Decimal(r["calc_footing_cost"])
             for r in client.get(f"/api/wall-runs?section_id={s.id}").json()}
    assert after == ftg_before


def test_a_typo_on_a_section_patch_is_a_422(client, db, estimate):
    """A silent 200 on an unknown field is how the hole above stayed invisible."""
    r = client.post(
        f"/api/estimates/{estimate.id}/sections",
        json={"kind": "walls_footings", "name": "W2", "unit": "FF"},
    )
    sid = r.json()["id"]
    bad = client.patch(f"/api/sections/{sid}", json={"footing_mix_desgin_id": 7})
    assert bad.status_code == 422, bad.text


def test_a_walls_section_can_carry_a_rebar_quote(client, db, estimate):
    """Walls buy bar like every other assembly — they were left out of STEEL_KINDS."""
    r = client.post(
        f"/api/estimates/{estimate.id}/sections",
        json={"kind": "walls_footings", "name": "W3", "unit": "FF"},
    )
    assert "rebar" in r.json()["quote_kinds"]
    q = client.put(
        f"/api/sections/{r.json()['id']}/quotes/rebar",
        json={"amount": "1240", "unit": "TON"},
    )
    assert q.status_code == 200, q.text
