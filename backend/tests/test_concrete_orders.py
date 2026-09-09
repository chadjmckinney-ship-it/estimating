"""
Concrete orders (sql/086, 2026-09-09).

Chad: "another section under daily reports... 'concrete orders' basically
like a daily report.. Date ordered, dropdown for job, concrete supplier,
date of pour, Time of pour, Yards ordered, mix design, order number, ordered
by. then the list and calender." On the mix: "mix design will be entered...
each supplier has mix numbers".

Pinned here: an order files with every field, today and the signed-in
person filled in when left blank; the list soonest pour first and its
filters; an edit; the delete rule (a senior's); the foreman files and reads
and does nothing else; a misspelled field, zero yards and an unknown job
refused.
"""

from __future__ import annotations

from decimal import Decimal

from app import policy

D = Decimal


def _job_id(client, name: str) -> int:
    return next(j["id"] for j in client.get("/api/daily-reports/meta").json()["jobs"] if j["name"] == name)


def _order(client, **over) -> dict:
    body = {
        "ordered_on": "2026-09-09", "job_id": _job_id(client, "NORTHWEST VILLAGE"), "supplier": "Cowtown",
        "pour_date": "2026-09-11", "pour_time": "07:00", "yards": "42.5", "mix": "4000-3A", "order_number": "CT-88231",
        "ordered_by": "Jorge", "notes": "Pump on site by 6.", "status": "ordered",
    }
    body.update(over)
    r = client.post("/api/concrete-orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_an_order_files_with_every_field_and_the_blanks_filled(client):
    o = _order(client)
    assert (o["job_name"], o["supplier"], o["pour_date"], o["pour_time"], D(o["yards"])) == (
        "NORTHWEST VILLAGE", "Cowtown", "2026-09-11", "07:00:00", D("42.5")
    )
    assert (o["mix"], o["order_number"], o["ordered_by"], o["status"], o["created_by_name"]) == (
        "4000-3A", "CT-88231", "Jorge", "ordered", "Test admin"
    )
    # Date ordered and ordered by fall in when left blank: today, and the signed-in person.
    p = _order(client, ordered_on="", ordered_by="", pour_time="", mix="", order_number="", notes="")
    assert p["ordered_by"] == "Test admin" and p["ordered_on"] and p["pour_time"] is None and p["mix"] is None
    assert client.get(f"/api/concrete-orders/{o['id']}").json()["id"] == o["id"]
    assert client.get("/api/concrete-orders/meta/statuses").json() == ["ordered", "confirmed", "poured", "canceled"]


def test_the_list_soonest_pour_first_and_its_filters(client):
    nw, md = _job_id(client, "NORTHWEST VILLAGE"), _job_id(client, "MANHEIM DALLAS")
    a = _order(client, pour_date="2026-09-12", job_id=nw)
    b = _order(client, pour_date="2026-09-10", pour_time="13:00", job_id=md, supplier="Martin Marietta", status="confirmed",
               mix="MM 3500 air", order_number="MM-1")
    c = _order(client, pour_date="2026-09-10", pour_time="06:30", job_id=nw, status="canceled", notes="Rain")
    ids = lambda path: [x["id"] for x in client.get(path).json()]  # noqa: E731
    assert ids("/api/concrete-orders") == [c["id"], b["id"], a["id"]], "by pour date, then the hour"
    assert ids(f"/api/concrete-orders?job_id={md}") == [b["id"]]
    assert ids("/api/concrete-orders?supplier=martin") == [b["id"]]
    assert ids("/api/concrete-orders?status=canceled") == [c["id"]]
    assert ids("/api/concrete-orders?date_from=2026-09-11") == [a["id"]]
    assert ids("/api/concrete-orders?date_to=2026-09-10") == [c["id"], b["id"]]
    assert ids("/api/concrete-orders?q=MM-1") == [b["id"]]
    assert ids("/api/concrete-orders?q=manheim") == [b["id"]]
    assert ids("/api/concrete-orders?q=rain") == [c["id"]]
    assert ids("/api/concrete-orders?limit=1&offset=1") == [b["id"]]


def test_an_edit_and_the_delete_rule(client, as_role):
    o = _order(client)
    e = client.patch(f"/api/concrete-orders/{o['id']}", json={"yards": "50", "status": "poured", "pour_time": "", "mix": ""}).json()
    assert (D(e["yards"]), e["status"], e["pour_time"], e["mix"]) == (D("50"), "poured", None, None)
    assert client.patch(f"/api/concrete-orders/{o['id']}", json={"supplier": ""}).json()["supplier"] == "Cowtown", "blank keeps it"
    est = as_role("estimator")
    assert est.patch(f"/api/concrete-orders/{o['id']}", json={"notes": "moved to Friday"}).status_code == 200
    r = est.delete(f"/api/concrete-orders/{o['id']}")
    assert r.status_code == 403 and "a senior estimator or above" in r.json()["detail"], r.text
    assert as_role("senior_estimator").delete(f"/api/concrete-orders/{o['id']}").status_code == 204
    assert client.get(f"/api/concrete-orders/{o['id']}").status_code == 404


def test_a_foreman_files_and_reads_and_nothing_else(db, as_role):
    foreman = as_role("foreman")
    job = foreman.get("/api/daily-reports/meta").json()["jobs"][0]["id"]
    r = foreman.post("/api/concrete-orders", json={"job_id": job, "supplier": "SRM", "pour_date": "2026-09-12", "yards": 20})
    assert r.status_code == 201, r.text
    assert r.json()["ordered_by"] == "Test foreman"
    assert foreman.get("/api/concrete-orders").status_code == 200
    assert foreman.get(f"/api/concrete-orders/{r.json()['id']}").status_code == 200
    for method, path, body in (
        ("patch", f"/api/concrete-orders/{r.json()['id']}", {"yards": 30}),
        ("delete", f"/api/concrete-orders/{r.json()['id']}", None),
    ):
        resp = getattr(foreman, method)(path, json=body) if body is not None else getattr(foreman, method)(path)
        assert resp.status_code == 403 and "a foreman" in resp.json()["detail"], resp.text
    assert policy.allowed("foreman", "GET", "/api/concrete-orders") and policy.allowed("foreman", "POST", "/api/concrete-orders")
    assert not policy.allowed("foreman", "PATCH", "/api/concrete-orders/x")
    assert policy.needed("DELETE", "/api/concrete-orders/x") == "senior_estimator"
    assert policy.needed("POST", "/api/concrete-orders") == "estimator" and policy.needed("GET", "/api/concrete-orders") == "user"


def test_what_is_refused(client):
    job = _job_id(client, "Office")
    ok = {"job_id": job, "supplier": "Cowtown", "pour_date": "2026-09-12", "yards": 10}
    assert client.post("/api/concrete-orders", json=dict(ok, yard=10)).status_code == 422
    assert client.post("/api/concrete-orders", json=dict(ok, yards=0)).status_code == 422
    assert client.post("/api/concrete-orders", json=dict(ok, status="maybe")).status_code == 422
    assert client.post("/api/concrete-orders", json=dict(ok, supplier="")).status_code == 422
    assert client.post("/api/concrete-orders", json=dict(ok, job_id=999999)).status_code == 400
