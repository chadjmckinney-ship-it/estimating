"""
The Notion bridge (2026-09-09; Chad: "bridge first, build it"): a Notion API
page becomes the row the bid import reads, and the import files it.

Pinned here: the three shapes the API returned on 2026-09-09 (a due date as
a day, a due date with a Central-time hour, the multi-select estimators and
types, the rich-text notes and message id, the url), a page with nothing
filled in, and the end-to-end import with its rerun.
"""

from __future__ import annotations

from app.services.bid_requests import normalise_row
from pull_notion_bids import page_to_row, read_env


def _rt(text: str) -> dict:
    return {"type": "rich_text", "rich_text": [{"plain_text": text}]}


PAGES = [
    {
        "url": "https://app.notion.com/p/Carter-Park-East-Phase-5-3d1a02768bd78141a66ed4a8732c67e5",
        "archived": False,
        "properties": {
            "Project Name": {"type": "title", "title": [{"plain_text": "Carter Park East "}, {"plain_text": "(Phase 5)"}]},
            "Status": {"type": "status", "status": {"name": "Not started"}},
            "Estimator": {"type": "multi_select", "multi_select": [{"name": "Chad"}, {"name": "Sam"}]},
            "GC": _rt("Ridgemont Commercial Construction"),
            "Location": _rt("Oak Grove Rd & Joel East Rd, Fort Worth, TX 76140"),
            "Project Type": {"type": "multi_select", "multi_select": [{"name": "Warehouse"}]},
            "Bid Due": {"type": "date", "date": {"start": "2026-09-16T17:00:00.000-05:00", "end": None, "time_zone": None}},
            "Bid Date": {"type": "date", "date": {"start": "2026-09-04", "end": None, "time_zone": None}},
            "Rev date": {"type": "date", "date": None},
            "Link to plans": {"type": "url", "url": "https://www.ridgemontestimating.com?accesskey=31D4513B22#projects/520946"},
            "Bid Price": {"type": "number", "number": None},
            "Rev Price": {"type": "number", "number": None},
            "Notes": _rt("SHORT BID TURNAROUND. Ground-up construction of (2) industrial tilt-wall buildings."),
            "Message ID": _rt("AAMkADczZDZi-carter"),
            "Parking Garage Foundation SF": {"type": "formula", "formula": {"type": "string", "string": None}},
        },
    },
    {
        "url": "https://app.notion.com/p/Moody-Center-Recording-Studio-3d6a02768bd781ef8241d85be208e096",
        "archived": False,
        "properties": {
            "Project Name": {"type": "title", "title": [{"plain_text": "Moody Center Recording Studio"}]},
            "Status": {"type": "status", "status": {"name": "Cancelation"}},
            "Estimator": {"type": "multi_select", "multi_select": [{"name": "Chad"}]},
            "GC": _rt("The Burt Group"),
            "Location": _rt(""),
            "Project Type": {"type": "multi_select", "multi_select": []},
            "Bid Due": {"type": "date", "date": {"start": "2026-09-11", "end": None, "time_zone": None}},
            "Bid Date": {"type": "date", "date": {"start": "2026-09-09", "end": None, "time_zone": None}},
            "Link to plans": {"type": "url", "url": "https://securecc.smartbidnet.com/LCYY"},
            "Bid Price": {"type": "number", "number": 148412.98},
            "Notes": _rt("100% CD's Added. Bid Due 9/11/2026 @5pm."),
            "Message ID": _rt("AAMkADczZDZi-moody"),
        },
    },
    {
        "url": "https://app.notion.com/p/Untitled-3d6a02768bd7817c966ef68080b5194e",
        "archived": False,
        "properties": {"Project Name": {"type": "title", "title": []}, "Status": {"type": "status", "status": None}},
    },
]


def test_a_page_becomes_the_row_the_import_reads():
    row = page_to_row(PAGES[0])
    assert row["Project Name"] == "Carter Park East (Phase 5)" and row["Status"] == "Not started"
    assert row["Estimator"] == ["Chad", "Sam"] and row["Project Type"] == ["Warehouse"]
    assert (row["date:Bid Due:start"], row["date:Bid Due:is_datetime"]) == ("2026-09-16T17:00:00.000-05:00", 1)
    assert (row["date:Bid Date:start"], row["date:Rev date:start"]) == ("2026-09-04", "")
    assert row["Message ID"] == "AAMkADczZDZi-carter" and row["url"].endswith("3d1a02768bd78141a66ed4a8732c67e5")

    f = normalise_row(row)
    assert (f["name"], f["gc"], f["status"], f["project_types"]) == (
        "Carter Park East (Phase 5)", "Ridgemont Commercial Construction", "not_started", ["Warehouse"]
    )
    assert (str(f["bid_due"]), str(f["bid_due_time"]), str(f["bid_date"])) == ("2026-09-16", "17:00:00", "2026-09-04")
    assert f["plans_url"].startswith("https://www.ridgemontestimating.com") and f["estimator_names"] == ["Chad", "Sam"]
    assert f["notion_page_id"] == "3d1a0276-8bd7-8141-a66e-d4a8732c67e5" and f["message_id"] == "AAMkADczZDZi-carter"

    g = normalise_row(page_to_row(PAGES[1]))
    assert (g["status"], g["bid_due_time"], str(g["bid_price"]), g["location"]) == ("canceled", None, "148412.98", None)

    h = normalise_row(page_to_row(PAGES[2]))
    assert (h["name"], h["status"], h["bid_due"], h["estimator_names"]) == ("(untitled)", "not_started", None, [])


def test_the_env_file_is_read_and_the_view_suffix_dropped(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    env = tmp_path / ".env"
    env.write_text('NOTION_TOKEN="ntn_secret"\nNOTION_DATABASE_ID=5162f7ae-bc79-495c-abeb-d51ae891725c?v=78ff2e\n', encoding="utf-8")
    got = read_env(str(env))
    assert got == {"NOTION_TOKEN": "ntn_secret", "NOTION_DATABASE_ID": "5162f7aebc79495cabebd51ae891725c"}


def test_the_bridge_files_the_pages_and_reruns_quietly(client, db):
    from app.services.bid_requests import import_rows  # noqa: PLC0415

    rows = [page_to_row(p) for p in PAGES]
    first = import_rows(db, rows)
    assert (first["created"], first["updated"], first["skipped"]) == (3, 0, 0)
    db.flush()
    listed = {b["name"]: b for b in client.get("/api/bid-requests").json()}
    carter = listed["Carter Park East (Phase 5)"]
    assert (carter["bid_due"], carter["bid_due_time"], carter["estimator_names"]) == ("2026-09-16", "17:00:00", ["Chad", "Sam"])
    assert listed["Moody Center Recording Studio"]["status"] == "canceled"

    again = import_rows(db, rows)
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 3)
