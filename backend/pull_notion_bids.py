"""
Pull the Notion "Concrete Estimating Bid list" onto the app's bid list (sql/082) — the bridge.

    .venv/bin/python backend/pull_notion_bids.py                # pull and write
    .venv/bin/python backend/pull_notion_bids.py --dry-run      # report, write nothing
    .venv/bin/python backend/pull_notion_bids.py --json-out ~/estimating/notion

Chad, 2026-09-09: "to either set bid invites straight into the app or...
automate imports from notion" — "bridge first, build it". The grok.com task
keeps writing invites to Notion as it does today; this pulls Notion into
the app every hour (notion-bids-pull.timer on the box) with the import that
already handles reruns, so a bid edited in the app is left alone and a
message id already on the list is a duplicate, not a second row. Notion
stays a relay until the invites come straight in; then it goes.

The token and the database id come from the bid-sync folder's .env
(NOTION_TOKEN, NOTION_DATABASE_ID — the "?v=..." view suffix is dropped), or
from the environment. Never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.bid_requests import import_rows  # noqa: E402

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"
ENV_FILES = ("~/gmail-bid-notion-sync/.env", "~/notion/notion-jotform.env", "~/.config/notion-jotform.env")


def read_env(explicit: str | None) -> dict[str, str]:
    """NOTION_TOKEN and NOTION_DATABASE_ID: the environment first, then the first env file that has them."""
    out = {k: os.environ[k] for k in ("NOTION_TOKEN", "NOTION_DATABASE_ID") if os.environ.get(k)}
    for candidate in ([explicit] if explicit else []) + list(ENV_FILES):
        p = Path(candidate).expanduser()
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip()
                if k in ("NOTION_TOKEN", "NOTION_DATABASE_ID") and k not in out:
                    out[k] = v.strip().strip('"').strip("'")
        if "NOTION_TOKEN" in out and "NOTION_DATABASE_ID" in out:
            break
    if "NOTION_DATABASE_ID" in out:
        out["NOTION_DATABASE_ID"] = out["NOTION_DATABASE_ID"].split("?")[0].replace("-", "")
    return out


def fetch_pages(token: str, database_id: str) -> list[dict]:
    """Every page of the database's data source, a hundred at a time."""
    import requests  # noqa: PLC0415 — the box's need, not the app's

    headers = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = requests.get(f"{API}/databases/{database_id}", headers=headers, timeout=60)
    db.raise_for_status()
    sources = db.json().get("data_sources") or []
    if not sources:
        raise RuntimeError("the database has no data source (is the token shared with it?)")
    ds = sources[0]["id"]
    pages: list[dict] = []
    cursor = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(f"{API}/data_sources/{ds}/query", headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        pages.extend(p for p in data.get("results", []) if not p.get("archived"))
        if not data.get("has_more"):
            return pages
        cursor = data.get("next_cursor")


def _text(prop: dict) -> str:
    kind = prop.get("type")
    parts = prop.get(kind) or []
    if kind in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in parts).strip()
    return ""


def _names(prop: dict) -> list[str]:
    kind = prop.get("type")
    if kind == "multi_select":
        return [o.get("name", "") for o in prop.get("multi_select") or [] if o.get("name")]
    if kind == "people":
        return [u.get("name", "") for u in prop.get("people") or [] if u.get("name")]
    if kind in ("select", "status"):
        v = (prop.get(kind) or {}).get("name")
        return [v] if v else []
    return []


def _date(prop: dict) -> tuple[str, int]:
    """(start, is_datetime) — the start as Notion writes it; a T in it means an hour was set."""
    start = ((prop.get("date") or {}).get("start") or "").strip()
    return start, 1 if "T" in start else 0


def _number(prop: dict):
    return prop.get("number")


def page_to_row(page: dict) -> dict[str, Any]:
    """A Notion API page as the rows-mode export the import reads (app.services.bid_requests.normalise_row)."""
    p = page.get("properties") or {}
    g = lambda name: p.get(name) or {}  # noqa: E731
    due, due_dt = _date(g("Bid Due"))
    received, _ = _date(g("Bid Date"))
    rev, _ = _date(g("Rev date"))
    return {
        "Project Name": _text(g("Project Name")),
        "Status": (_names(g("Status")) or [""])[0],
        "Estimator": _names(g("Estimator")),
        "GC": _text(g("GC")),
        "Location": _text(g("Location")),
        "Project Type": _names(g("Project Type")),
        "date:Bid Due:start": due,
        "date:Bid Due:is_datetime": due_dt,
        "date:Bid Date:start": received,
        "date:Rev date:start": rev,
        "Link to plans": (g("Link to plans").get("url") or "").strip(),
        "Bid Price": _number(g("Bid Price")),
        "Rev Price": _number(g("Rev Price")),
        "Notes": _text(g("Notes")),
        "Message ID": _text(g("Message ID")),
        "url": page.get("url") or "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", help="where NOTION_TOKEN and NOTION_DATABASE_ID live (default: the bid-sync .env)")
    ap.add_argument("--json-out", type=Path, help="keep the raw pages here, one file per pull")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, write nothing")
    ap.add_argument("--database-url", default=settings.database_url)
    args = ap.parse_args()

    env = read_env(args.env_file)
    if "NOTION_TOKEN" not in env or "NOTION_DATABASE_ID" not in env:
        print("no NOTION_TOKEN / NOTION_DATABASE_ID: --env-file, the environment, or one of " + ", ".join(ENV_FILES), file=sys.stderr)
        return 2
    print(f"database: {args.database_url.split('@')[-1]}")
    pages = fetch_pages(env["NOTION_TOKEN"], env["NOTION_DATABASE_ID"])
    print(f"Notion: {len(pages)} pages")
    if args.json_out:
        args.json_out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (args.json_out / f"notion-bids-{stamp}.json").write_text(json.dumps(pages), encoding="utf-8")
    rows = [page_to_row(pg) for pg in pages]

    engine = create_engine(args.database_url)
    with Session(engine, autoflush=False) as db:
        result = import_rows(db, rows)
        if args.dry_run:
            db.rollback()
            print("dry run — nothing written")
        else:
            db.commit()
    print(
        f"created {result['created']}, updated {result['updated']}, unchanged {result['unchanged']}, "
        f"skipped {result['skipped']}"
    )
    if result["unknown_estimators"]:
        print("estimators not matched to people:", ", ".join(result["unknown_estimators"]))
    if result["duplicates"]:
        print(f"{len(result['duplicates'])} possible duplicate(s) (listed, not merged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
