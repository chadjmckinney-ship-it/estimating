"""
The three catalogs' CRUD routes — mix designs, materials, equipment — had no
test (audit 2026-09-04, P3 — batch 4, 2026-09-06).

What they promise: create echoes the row and normalises what it strips and
upper-cases; a duplicate is a 409, not a 500; an unknown id is a 404; a
misspelled field is a 422 (P2 #8); a delete deactivates rather than removes,
so the default list drops the row and `active_only=false` still shows it —
costing matches materials by name and forming lines keep a material_id.
"""

from __future__ import annotations

from decimal import Decimal

D = Decimal


def test_mix_designs_round_trip(client):
    body = {"code": " TEST-MIX-9 ", "name": " Test mix 9 ", "strength_psi": 4000, "unit_cost": "150.00"}
    r = client.post("/api/mix-designs", json=body)
    assert r.status_code == 201, r.text
    mix = r.json()
    assert (mix["code"], mix["name"]) == ("TEST-MIX-9", "Test mix 9")
    assert D(mix["unit_cost"]) == D("150.00")
    assert client.post("/api/mix-designs", json=body).status_code == 409

    assert client.get(f"/api/mix-designs/{mix['id']}").json()["name"] == "Test mix 9"
    assert client.get("/api/mix-designs/999999").status_code == 404

    r = client.patch(f"/api/mix-designs/{mix['id']}", json={"unit_cost": "160.00", "name": " Test mix 9b "})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Test mix 9b" and D(r.json()["unit_cost"]) == D("160.00")
    assert client.patch(f"/api/mix-designs/{mix['id']}", json={"strength_psi": 500}).status_code == 422
    assert client.patch(f"/api/mix-designs/{mix['id']}", json={"nmae": "x"}).status_code == 422
    assert client.patch("/api/mix-designs/999999", json={"name": "x"}).status_code == 404

    assert client.delete(f"/api/mix-designs/{mix['id']}").status_code == 204
    assert mix["id"] not in {m["id"] for m in client.get("/api/mix-designs").json()}
    assert mix["id"] in {m["id"] for m in client.get("/api/mix-designs?active_only=false").json()}
    assert client.delete("/api/mix-designs/999999").status_code == 404


def test_materials_round_trip(client):
    body = {"name": " TEST WIDGET 9 ", "category": "lumber", "unit": "ea", "unit_cost": "2.50"}
    r = client.post("/api/materials", json=body)
    assert r.status_code == 201, r.text
    mat = r.json()
    assert (mat["name"], mat["unit"], mat["category"]) == ("TEST WIDGET 9", "EA", "lumber")
    assert client.post("/api/materials", json=body).status_code == 409

    r = client.post("/api/materials", json={**body, "name": "TEST WIDGET 9 NOPE", "category": "nope"})
    assert r.status_code == 409 and "category" in r.json()["detail"], r.text

    assert "lumber" in client.get("/api/materials/meta/categories").json()
    assert mat["id"] in {m["id"] for m in client.get("/api/materials?category=lumber").json()}
    assert mat["id"] in {m["id"] for m in client.get("/api/materials?q=widget").json()}
    assert client.get("/api/materials/999999").status_code == 404

    r = client.patch(f"/api/materials/{mat['id']}", json={"unit": "box", "unit_cost": "3.00"})
    assert r.status_code == 200 and r.json()["unit"] == "BOX", r.text
    assert client.patch(f"/api/materials/{mat['id']}", json={"unit_cost": "-1"}).status_code == 422
    assert client.patch(f"/api/materials/{mat['id']}", json={"unti": "EA"}).status_code == 422

    assert client.delete(f"/api/materials/{mat['id']}").status_code == 204
    assert mat["id"] not in {m["id"] for m in client.get("/api/materials").json()}
    assert mat["id"] in {m["id"] for m in client.get("/api/materials?active_only=false").json()}
    assert client.delete("/api/materials/999999").status_code == 404


def test_equipment_round_trip(client):
    body = {"name": " TEST CRANE 9 ", "category": "lifting", "unit": "day", "unit_cost": "900"}
    r = client.post("/api/equipment", json=body)
    assert r.status_code == 201, r.text
    eq = r.json()
    assert (eq["name"], eq["unit"], eq["category"]) == ("TEST CRANE 9", "DAY", "lifting")
    assert client.post("/api/equipment", json=body).status_code == 409
    assert client.post("/api/equipment", json={**body, "name": "X", "category": "flying"}).status_code == 422

    cats = client.get("/api/equipment/meta/categories").json()
    assert set(cats) == {"earthwork", "lifting", "power", "hauling", "pumping", "other"}
    assert eq["id"] in {e["id"] for e in client.get("/api/equipment?category=lifting").json()}
    assert client.get("/api/equipment/999999").status_code == 404

    r = client.patch(f"/api/equipment/{eq['id']}", json={"unit_cost": "950", "code": " tc-9 "})
    assert r.status_code == 200 and r.json()["code"] == "TC-9" and D(r.json()["unit_cost"]) == D("950"), r.text
    assert client.patch(f"/api/equipment/{eq['id']}", json={"cateogry": "other"}).status_code == 422

    assert client.delete(f"/api/equipment/{eq['id']}").status_code == 204
    assert eq["id"] not in {e["id"] for e in client.get("/api/equipment").json()}
    assert eq["id"] in {e["id"] for e in client.get("/api/equipment?active_only=false").json()}
    assert client.delete("/api/equipment/999999").status_code == 404
