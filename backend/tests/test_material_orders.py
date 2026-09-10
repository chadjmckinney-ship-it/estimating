"""
Material orders (sql/087, 2026-09-09).

Chad: "the next section... this is going to be like concrete orders.. but
materials.. mostly to track post tension and rebar for projects.. so
actually concrete orders should be there too..."; on the shape, "build it".

Pinned here: an order files with every field, today and the signed-in
person filled in when left blank, the unit uppercased, delivered filling
its date; the list by needed-by date and its filters; the summary by job,
kind and unit; the meta with the suppliers used before; an edit and the
delete rule; the foreman files and reads and nothing else; what is refused.
"""

from __future__ import annotations

from decimal import Decimal

from app import policy

D = Decimal


def _job_id(client, name: str) -> int:
    return next(j["id"] for j in client.get("/api/daily-reports/meta").json()["jobs"] if j["name"] == name)


def _order(client, **over) -> dict:
    body = {
        "kind": "rebar", "ordered_on": "2026-09-09", "job_id": _job_id(client, "NORTHWEST VILLAGE"), "supplier": "CMC",
        "description": "#5 x 20' straight, #4 x 20' — per shop drawings sheet S-3", "quantity": "12.5", "unit": "ton",
        "needed_by": "2026-09-15", "order_number": "CMC-4471", "ordered_by": "Chad", "notes": "Deliver to the east gate.",
        "status": "ordered",
    }
    body.update(over)
    r = client.post("/api/material-orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_an_order_files_with_every_field_and_the_blanks_filled(client):
    o = _order(client)
    assert (o["kind"], o["job_name"], o["supplier"], D(o["quantity"]), o["unit"], o["needed_by"]) == (
        "rebar", "NORTHWEST VILLAGE", "CMC", D("12.5"), "TON", "2026-09-15"
    )
    assert (o["order_number"], o["ordered_by"], o["status"], o["delivered_on"], o["created_by_name"]) == (
        "CMC-4471", "Chad", "ordered", None, "Test admin"
    )
    p = _order(client, kind="post_tension", ordered_on="", ordered_by="", quantity="", unit="", needed_by="",
               order_number="", notes="", description="PT cable 1/2\" per Suncoast shop drawings")
    assert p["ordered_by"] == "Test admin" and p["ordered_on"] and p["quantity"] is None and p["unit"] is None
    d = _order(client, status="delivered")
    assert d["delivered_on"] is not None, "delivered fills its date when none is given"
    assert client.get(f"/api/material-orders/{o['id']}").json()["id"] == o["id"]


def test_the_list_by_needed_by_and_its_filters(client):
    nw, md = _job_id(client, "NORTHWEST VILLAGE"), _job_id(client, "MANHEIM DALLAS")
    a = _order(client, needed_by="2026-09-20", job_id=nw)
    b = _order(client, kind="post_tension", needed_by="2026-09-12", job_id=md, supplier="Suncoast", status="confirmed",
               description="PT tendons per S-5", order_number="SC-9")
    c = _order(client, kind="other", needed_by=None, job_id=nw, supplier="Whitecap", description="Chairs and dobies",
               status="canceled", notes="Rain")
    ids = lambda path: [x["id"] for x in client.get(path).json()]  # noqa: E731
    assert ids("/api/material-orders") == [b["id"], a["id"], c["id"]], "needed-by first, nothing needed last"
    assert ids("/api/material-orders?kind=post_tension") == [b["id"]]
    assert ids(f"/api/material-orders?job_id={md}") == [b["id"]]
    assert ids("/api/material-orders?supplier=white") == [c["id"]]
    assert ids("/api/material-orders?status=canceled") == [c["id"]]
    assert ids("/api/material-orders?date_from=2026-09-15") == [a["id"]]
    assert ids("/api/material-orders?date_to=2026-09-15") == [b["id"]]
    assert ids("/api/material-orders?q=SC-9") == [b["id"]]
    assert ids("/api/material-orders?q=manheim") == [b["id"]]
    assert ids("/api/material-orders?q=chairs") == [c["id"]]
    assert ids("/api/material-orders?limit=1&offset=1") == [a["id"]]


def test_the_summary_by_job_kind_and_unit_and_the_meta(client):
    nw, md = _job_id(client, "NORTHWEST VILLAGE"), _job_id(client, "MANHEIM DALLAS")
    _order(client, job_id=nw, quantity="12.5", unit="TON")
    _order(client, job_id=nw, quantity="4", unit="ton", supplier="CMC")
    _order(client, job_id=nw, kind="post_tension", quantity="18500", unit="LF", supplier="Suncoast", description="PT")
    _order(client, job_id=md, quantity="2", unit="TON", supplier="Whitecap")
    _order(client, job_id=md, quantity="99", unit="TON", status="canceled")  # left out
    rows = client.get("/api/material-orders/summary").json()
    assert [(r["job_name"], r["kind"], r["unit"], r["orders"], D(r["quantity"])) for r in rows] == [
        ("MANHEIM DALLAS", "rebar", "TON", 1, D("2")),
        ("NORTHWEST VILLAGE", "post_tension", "LF", 1, D("18500")),
        ("NORTHWEST VILLAGE", "rebar", "TON", 2, D("16.5")),
    ]
    assert [r["kind"] for r in client.get(f"/api/material-orders/summary?job_id={nw}&kind=rebar").json()] == ["rebar"]
    meta = client.get("/api/material-orders/meta").json()
    assert [k["key"] for k in meta["kinds"]] == ["rebar", "post_tension", "other"] and meta["kinds"][1]["es"] == "Postensado"
    assert "TON" in meta["units"] and meta["statuses"] == ["ordered", "confirmed", "delivered", "canceled"]
    assert meta["suppliers"][0] == "Whitecap" and set(meta["suppliers"]) == {"CMC", "Suncoast", "Whitecap"}, "most recent first"


def test_an_edit_and_the_delete_rule(client, as_role):
    o = _order(client)
    e = client.patch(f"/api/material-orders/{o['id']}", json={"quantity": "14", "unit": "ton", "status": "delivered", "notes": ""}).json()
    assert (D(e["quantity"]), e["unit"], e["status"], e["notes"]) == (D("14"), "TON", "delivered", None)
    assert e["delivered_on"] is not None
    assert client.patch(f"/api/material-orders/{o['id']}", json={"supplier": "", "description": ""}).json()["supplier"] == "CMC", "blank keeps it"
    est = as_role("estimator")
    assert est.patch(f"/api/material-orders/{o['id']}", json={"notes": "moved to Friday"}).status_code == 200
    r = est.delete(f"/api/material-orders/{o['id']}")
    assert r.status_code == 403 and "a senior estimator or above" in r.json()["detail"], r.text
    assert as_role("senior_estimator").delete(f"/api/material-orders/{o['id']}").status_code == 204
    assert client.get(f"/api/material-orders/{o['id']}").status_code == 404


def test_a_foreman_files_and_reads_and_nothing_else(db, as_role):
    foreman = as_role("foreman")
    job = foreman.get("/api/daily-reports/meta").json()["jobs"][0]["id"]
    r = foreman.post("/api/material-orders", json={"kind": "rebar", "job_id": job, "supplier": "CMC", "description": "#4 x 20'", "quantity": 2, "unit": "ton"})
    assert r.status_code == 201, r.text
    assert r.json()["ordered_by"] == "Test foreman"
    assert foreman.get("/api/material-orders").status_code == 200
    assert foreman.get("/api/material-orders/meta").status_code == 200
    for method, path, body in (
        ("patch", f"/api/material-orders/{r.json()['id']}", {"quantity": 3}),
        ("delete", f"/api/material-orders/{r.json()['id']}", None),
    ):
        resp = getattr(foreman, method)(path, json=body) if body is not None else getattr(foreman, method)(path)
        assert resp.status_code == 403 and "a foreman" in resp.json()["detail"], resp.text
    assert policy.allowed("foreman", "GET", "/api/material-orders") and policy.allowed("foreman", "POST", "/api/material-orders")
    assert not policy.allowed("foreman", "PATCH", "/api/material-orders/x")
    assert policy.needed("DELETE", "/api/material-orders/x") == "senior_estimator"


def test_what_is_refused(client):
    job = _job_id(client, "Office")
    ok = {"kind": "rebar", "job_id": job, "supplier": "CMC", "description": "#4"}
    assert client.post("/api/material-orders", json=dict(ok, kinds="rebar")).status_code == 422
    assert client.post("/api/material-orders", json=dict(ok, kind="lumber")).status_code == 422
    assert client.post("/api/material-orders", json=dict(ok, quantity=-1)).status_code == 422
    assert client.post("/api/material-orders", json=dict(ok, status="lost")).status_code == 422
    assert client.post("/api/material-orders", json=dict(ok, description="")).status_code == 422
    assert client.post("/api/material-orders", json=dict(ok, job_id=999999)).status_code == 400
