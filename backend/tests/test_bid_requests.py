"""
The bid list (sql/082): every invite as it came in, apart from projects.

Chad, 2026-09-09: "instead of importing the notions database into projects
how about we create a new table and it be seperate so we are not scrolling
thru a ton of jobs to find the one i want.. then when we choose that we are
estimating, it gets copied over" — and, on the proposal, "build it".

Pinned here: a bid becomes a project with every field and the people
carried and the link both ways, and a second press is refused; a repeated
invite is refused on its message id; a Notion-shaped import counts, maps
and dedupes, and reruns without doubling; the list filters; a misspelled
field is a 422; a viewer reads and does not write.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.estimator import Estimator

D = Decimal


@pytest.fixture
def people(db) -> dict[str, Estimator]:
    rows = db.scalars(select(Estimator).where(Estimator.username.in_(["chad", "sam", "edward"]))).all()
    out = {e.username: e for e in rows}
    assert {"chad", "sam"} <= set(out), "sql/004 seeds the estimators"
    return out


def _bid(client, **over) -> dict:
    body = {
        "name": "EOS Fitness", "gc": "MYCON General Contractors", "location": "2640 Concord Dr, Forney, TX 75126",
        "project_types": ["Retail"], "status": "not_started", "bid_due": "2026-09-30", "bid_due_time": "17:00",
        "bid_date": "2026-09-04", "plans_url": "https://app.buildingconnected.com/goto/abc",
        "notes": "Bid invite via BuildingConnected for Concrete. 42,686 SF health club.",
        "message_id": "AAMkAD-eos-1", "estimator_ids": [],
    }
    body.update(over)
    r = client.post("/api/bid-requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_list_and_its_filters(client, db, people):
    chad, sam = people["chad"], people["sam"]
    a = _bid(client, estimator_ids=[str(chad.id), str(sam.id)])
    b = _bid(client, name="Andrews County Recreation Center", gc="Lee Lewis Construction, Inc.",
             location="Andrews, TX", status="canceled", bid_due="2026-09-22", message_id="AAMkAD-andrews",
             estimator_ids=[str(sam.id)])
    c = _bid(client, name="Bartlett's South", gc="Burt Group (TBG)", location=None, bid_due=None,
             message_id=None, notes="ITB from Burt Group. Bid Due 09/15/2026 at 5pm.")

    assert a["estimator_names"] == ["Chad", "Sam"] and a["bid_due_time"] == "17:00:00"
    rows = client.get("/api/bid-requests").json()
    # Soonest due first, no due date last.
    assert [r["id"] for r in rows] == [b["id"], a["id"], c["id"]]
    assert [r["id"] for r in client.get("/api/bid-requests?status=canceled").json()] == [b["id"]]
    assert [r["id"] for r in client.get(f"/api/bid-requests?estimator_id={chad.id}").json()] == [a["id"]]
    assert [r["id"] for r in client.get("/api/bid-requests?gc=lee%20lewis").json()] == [b["id"]]
    assert [r["id"] for r in client.get("/api/bid-requests?q=Forney").json()] == [a["id"]]
    assert [r["id"] for r in client.get("/api/bid-requests?q=Burt").json()] == [c["id"]]
    assert [r["id"] for r in client.get("/api/bid-requests?due_from=2026-09-23").json()] == [a["id"]]
    assert client.get("/api/bid-requests/meta/statuses").json() == [
        "not_started", "in_progress", "submitted", "awarded", "canceled",
    ]

    # Edit: the status in the row, the people, a blank clears a date.
    r = client.patch(f"/api/bid-requests/{a['id']}", json={"status": "submitted", "bid_price": 148412.98,
                                                          "estimator_ids": [str(sam.id)], "bid_due_time": ""})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["estimator_names"], r.json()["bid_due_time"]) == ("submitted", ["Sam"], None)
    assert D(str(r.json()["bid_price"])) == D("148412.98")
    assert client.delete(f"/api/bid-requests/{c['id']}").status_code == 204
    assert client.get(f"/api/bid-requests/{c['id']}").status_code == 404


def test_estimate_this_makes_the_project_and_links_it(client, db, people):
    chad, sam = people["chad"], people["sam"]
    bid = _bid(client, estimator_ids=[str(chad.id), str(sam.id)])
    assert bid["project_id"] is None

    r = client.post(f"/api/bid-requests/{bid['id']}/estimate")
    assert r.status_code == 200, r.text
    res = r.json()
    pid = res["project_id"]
    assert res["bid"]["project_id"] == pid and res["bid"]["project_name"] == "EOS Fitness"
    assert res["bid"]["status"] == "in_progress"   # was not started; now being estimated

    project = client.get(f"/api/projects/{pid}").json()
    for field in ("name", "gc", "location", "project_types", "bid_due", "bid_date", "plans_url", "notes"):
        assert project[field] == bid[field], field
    assert project["notion_message_id"] == bid["message_id"]
    assert project["status"] == "in_progress"
    assert set(project["estimator_ids"]) == {str(chad.id), str(sam.id)}
    assert any(p["id"] == pid for p in client.get("/api/projects").json())

    # A second press is refused; the bid still shows its project.
    assert client.post(f"/api/bid-requests/{bid['id']}/estimate").status_code == 409
    again = client.get(f"/api/bid-requests/{bid['id']}").json()
    assert again["project_id"] == pid

    # A bid already submitted keeps that status when it is estimated.
    other = _bid(client, name="Tractor Supply - Princeton, TX", message_id="AAMkAD-tsc", status="submitted")
    res = client.post(f"/api/bid-requests/{other['id']}/estimate").json()
    assert res["bid"]["status"] == "submitted"


def test_the_same_invite_is_not_entered_twice(client, db):
    _bid(client)
    r = client.post("/api/bid-requests", json={"name": "EOS Fitness again", "message_id": "AAMkAD-eos-1"})
    assert r.status_code == 409, r.text
    assert "message id" in r.json()["detail"]
    b = _bid(client, name="Other", message_id="AAMkAD-other")
    assert client.patch(f"/api/bid-requests/{b['id']}", json={"message_id": "AAMkAD-eos-1"}).status_code == 409


# ------------------------------------------------------------- import ----

NOTION_ROWS = [
    {   # the SQL mode's shape, a due with an hour, two people and a stranger
        "url": "https://app.notion.com/p/3d1a02768bd781ef98b5db3116f6a245", "createdTime": "2026-09-04T14:00:00.000Z",
        "name": "EOS Fitness", "status": "Not started", "estimators": "[\"Chad\",\"Sam\",\"Zed\"]",
        "gc": "MYCON General Contractors", "location": "2640 Concord Dr, Forney, TX 75126", "types": "[\"Retail\"]",
        "bid_due": "2026-09-16T22:00:00.000Z", "due_dt": 1, "bid_date": "2026-09-04",
        "plans": "https://app.buildingconnected.com/goto/6a99", "notes": "Bid invite via BuildingConnected for Concrete.<br>Contact: [Emma Ponder](mailto:eponder@mycon.com) \\| 972-555-0100",
        "message_id": "AAMkADczZDZi-eos", "bid_price": None, "rev_date": None, "rev_price": None,
    },
    {   # canceled, no hour, no plans, a price
        "url": "https://app.notion.com/p/3c1a02768bd781ec8c9bfba763b6f590", "createdTime": "2026-08-19T16:53:00.000Z",
        "name": "Andrews County Recreation Center", "status": "Cancelation", "estimators": "[\"Chad\"]",
        "gc": "Lee Lewis Construction, Inc.", "location": "Andrews, TX", "types": "[\"Commercial\"]",
        "bid_due": "2026-09-22", "due_dt": 0, "bid_date": "2026-08-19", "plans": "", "notes": "Invited for CONCRETE scope.",
        "message_id": "AAMkADczZDZi-andrews", "bid_price": 43000, "rev_date": "2026-08-30", "rev_price": 41000,
    },
    {   # the same job under the same GC a second time — the Tractor Supply pattern
        "url": "https://app.notion.com/p/3c1a02768bd7814080dedadb6f4279b0", "createdTime": "2026-08-19T16:53:00.000Z",
        "name": "Andrews County Recreation Center", "status": "Not started", "estimators": "[]",
        "gc": "Lee Lewis Construction, Inc.", "location": "Andrews, TX", "types": None,
        "bid_due": None, "due_dt": 0, "bid_date": None, "plans": None, "notes": None,
        "message_id": None, "bid_price": None, "rev_date": None, "rev_price": None,
    },
]


def test_a_notion_export_loads_and_reruns_without_doubling(client, db, people):
    r = client.post("/api/bid-requests/import", json=NOTION_ROWS)
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["created"], res["updated"], res["unchanged"], res["skipped"]) == (3, 0, 0, 0)
    assert res["unknown_estimators"] == ["Zed"]
    assert len(res["duplicates"]) == 1 and res["duplicates"][0].startswith("Andrews County Recreation Center")

    rows = {b["name"] + "|" + (b["message_id"] or ""): b for b in client.get("/api/bid-requests").json()}
    eos = rows["EOS Fitness|AAMkADczZDZi-eos"]
    # 22:00 UTC on the 16th is 5 PM in the office.
    assert (eos["bid_due"], eos["bid_due_time"]) == ("2026-09-16", "17:00:00")
    assert eos["notes"] == "Bid invite via BuildingConnected for Concrete.\nContact: Emma Ponder | 972-555-0100"
    assert eos["estimator_names"] == ["Chad", "Sam"]
    assert eos["notion_page_id"] == "3d1a0276-8bd7-81ef-98b5-db3116f6a245"
    assert eos["plans_url"].startswith("https://app.buildingconnected.com")
    andrews = rows["Andrews County Recreation Center|AAMkADczZDZi-andrews"]
    assert andrews["status"] == "canceled" and andrews["plans_url"] is None
    assert D(str(andrews["bid_price"])) == D("43000.00") and andrews["rev_date"] == "2026-08-30"

    # Run it again: nothing doubles; an untouched row takes Notion's values afresh,
    # and a row Notion did not change is left as it is.
    changed = [dict(NOTION_ROWS[0], notes="Rewritten in Notion"), NOTION_ROWS[1], NOTION_ROWS[2]]
    res = client.post("/api/bid-requests/import", json=changed).json()
    assert (res["created"], res["updated"], res["unchanged"], res["skipped"]) == (0, 1, 2, 0)
    assert len(client.get("/api/bid-requests").json()) == 3
    assert client.get(f"/api/bid-requests/{eos['id']}").json()["notes"] == "Rewritten in Notion"

    # A row edited here, or already estimated, is left alone on the next run.
    client.patch(f"/api/bid-requests/{andrews['id']}", json={"notes": "Chad's own words"})
    client.post(f"/api/bid-requests/{eos['id']}/estimate")
    res = client.post("/api/bid-requests/import", json=changed).json()
    assert (res["created"], res["updated"], res["unchanged"], res["skipped"]) == (0, 0, 1, 2)
    assert client.get(f"/api/bid-requests/{andrews['id']}").json()["notes"] == "Chad's own words"

    # A new page carrying a message id already on the list is the same invite: listed, not entered.
    again = dict(NOTION_ROWS[0], url="https://app.notion.com/p/11111111222233334444555555555555")
    res = client.post("/api/bid-requests/import", json=[again]).json()
    assert (res["created"], res["skipped"]) == (0, 1) and "same invite" in res["duplicates"][0]


def test_a_typo_is_a_422_and_a_viewer_only_reads(client, as_role, db):
    assert client.post("/api/bid-requests", json={"name": "x", "gcc": "y"}).status_code == 422
    b = _bid(client)
    assert client.patch(f"/api/bid-requests/{b['id']}", json={"statsu": "awarded"}).status_code == 422
    assert client.post("/api/bid-requests", json={"name": "x", "plans_url": "ftp://nope"}).status_code == 422
    viewer = as_role("user")
    assert viewer.get("/api/bid-requests").status_code == 200
    assert viewer.post("/api/bid-requests", json={"name": "x"}).status_code == 403
    assert viewer.post(f"/api/bid-requests/{b['id']}/estimate").status_code == 403
