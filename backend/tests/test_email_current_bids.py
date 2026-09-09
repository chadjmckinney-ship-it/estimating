"""
The 8:05 bid email read from the app's list instead of Notion (2026-09-09).

Pinned here: the open bids (not started, in progress) in the four sections
the Notion-era email had — overdue, due today, next seven days, later or
undated — soonest first, the hour when the invite named one, the people, the
plans link; and the subject that counts them.
"""

from __future__ import annotations

from datetime import date

from email_current_bids import format_report, open_bids


def _bid(client, **over) -> dict:
    body = {"name": "EOS Fitness", "gc": "MYCON", "status": "not_started", "bid_due": "2026-09-16", "message_id": None}
    body.update(over)
    r = client.post("/api/bid-requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_open_bids_in_their_sections(client, db):
    people = {p["username"]: p["id"] for p in client.get("/api/estimators").json()}
    today = date(2026, 9, 9)
    _bid(client, name="Andrews Rec Center", bid_due="2026-09-07", gc="Lee Lewis", location="Andrews, TX")
    _bid(client, name="Moody Center", bid_due="2026-09-09", bid_due_time="17:00", estimator_ids=[people["chad"]], plans_url="https://securecc.smartbidnet.com/LCYY")
    _bid(client, name="Carter Park East", bid_due="2026-09-16", bid_due_time="17:00", status="in_progress", project_types=["Warehouse"])
    _bid(client, name="Bartlett's South", bid_due=None, gc="Burt Group")
    _bid(client, name="Sherry Pointe", bid_due="2026-10-01")
    _bid(client, name="Done already", bid_due="2026-09-10", status="submitted")  # not open, not listed
    db.flush()

    rows = open_bids(db)
    assert [r["name"] for r in rows] == ["Andrews Rec Center", "Moody Center", "Carter Park East", "Sherry Pointe", "Bartlett's South"]
    subject, body = format_report(rows, today)
    assert subject == "Current bids — 2026-09-09: 5 open, 1 overdue, 1 due today, 1 due this week"
    assert "Total open: 5" in body
    assert "  Overdue: 1  |  Due today: 1  |  Next 7 days: 1  |  Later/undated: 2" in body
    assert "=== OVERDUE (1) ===\n1. Andrews Rec Center\n   Due:    2026-09-07  OVERDUE (2d)\n   Status: Not started\n   GC:     Lee Lewis\n   Loc:    Andrews, TX\n" in body
    assert "=== DUE TODAY (1) ===\n1. Moody Center\n   Due:    2026-09-09 5:00 PM  DUE TODAY\n" in body
    assert "   Est:    Chad\n   Plans:  https://securecc.smartbidnet.com/LCYY\n" in body
    assert "=== DUE IN NEXT 7 DAYS (1) ===\n1. Carter Park East\n   Due:    2026-09-16 5:00 PM  (in 7d)\n   Status: In progress\n   GC:     MYCON\n   Type:   Warehouse\n" in body
    assert "=== LATER / NO DUE DATE (2) ===\n1. Sherry Pointe\n   Due:    2026-10-01  (in 22d)\n" in body
    assert "2. Bartlett's South\n   Due:    no due date\n" in body
    assert "Done already" not in body and "The list: https://" in body


def test_an_empty_list_still_reads(db):
    subject, body = format_report([], date(2026, 9, 9))
    assert subject == "Current bids — 2026-09-09: 0 open"
    assert body.count("  (none)") == 4
