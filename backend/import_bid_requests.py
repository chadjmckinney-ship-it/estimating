"""
Load a Notion bid-list export onto the app's bid list (sql/082).

    .venv/bin/python backend/import_bid_requests.py bids_export.json
    .venv/bin/python backend/import_bid_requests.py bids_export.json --dry-run

The file is a JSON list of rows as the Notion MCP hands them over — either
its SQL mode (name, status, estimators, gc, location, types, bid_due, due_dt,
bid_date, plans, notes, message_id, bid_price, rev_date, rev_price, url) or
its rows mode ("Project Name", "Status", "date:Bid Due:start" ...). Both are
read by app.services.bid_requests.normalise_row.

Upserts by Notion page id, so it can run again before the cutover: a row
never touched in the app takes Notion's values afresh; one edited here, or
already estimated, is left alone and counted as skipped. Reads DATABASE_URL
the way the app does (the box's default is the peer-auth socket).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.bid_requests import import_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path, help="the JSON list of Notion rows")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, write nothing")
    ap.add_argument("--database-url", default=settings.database_url)
    args = ap.parse_args()

    rows = json.loads(args.export.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("results") or rows.get("rows") or []
    print(f"database: {args.database_url.split('@')[-1]}")
    print(f"rows in the export: {len(rows)}")

    engine = create_engine(args.database_url)
    with Session(engine, autoflush=False) as db:
        result = import_rows(db, rows)
        if args.dry_run:
            db.rollback()
            print("dry run — nothing written")
        else:
            db.commit()
    print(f"created {result['created']}, updated {result['updated']}, unchanged {result['unchanged']}, skipped {result['skipped']}")
    if result["unknown_estimators"]:
        print("estimators not matched to people:", ", ".join(result["unknown_estimators"]))
    if result["duplicates"]:
        print(f"{len(result['duplicates'])} possible duplicate(s):")
        for d in result["duplicates"]:
            print("  -", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
