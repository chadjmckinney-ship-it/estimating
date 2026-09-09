"""
Pull every daily report from Jotform into the app (sql/084).

    .venv/bin/python backend/import_daily_reports.py                 # both forms, from the Jotform API
    .venv/bin/python backend/import_daily_reports.py --dry-run
    .venv/bin/python backend/import_daily_reports.py --form 210626162682150
    .venv/bin/python backend/import_daily_reports.py --from-json saved.json --form 210626162682150

The API key is --key, JOTFORM_API_KEY in the environment, or the
JOTFORM_API_KEY line of the first of ~/.config/notion-jotform.env,
~/.notion-jotform.env and ~/notion/notion-jotform.env that exists (the
files the Notion importer read). It is never printed.

Upserts by submission id (app.services.daily_reports.import_submissions), so
it runs every hour on the office box until the crews use the app's form: a
submission never touched here takes Jotform's values afresh; one edited in
the app is left alone, and counted as skipped when Jotform's copy changed
too. --json-out keeps the raw fetch
beside the database's own dump, in case a question about the mapping comes
up later. Reads DATABASE_URL the way the app does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.daily_reports import NEW_FORM, OLD_FORM, import_submissions  # noqa: E402

API = "https://api.jotform.com"
PAGE = 1000
ENV_FILES = ("~/.config/notion-jotform.env", "~/.notion-jotform.env", "~/notion/notion-jotform.env")


def find_key(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    if os.environ.get("JOTFORM_API_KEY"):
        return os.environ["JOTFORM_API_KEY"].strip()
    for candidate in ENV_FILES:
        p = Path(candidate).expanduser()
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("JOTFORM_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fetch_all(form_id: str, key: str) -> list[dict]:
    """Every submission of the form, oldest first, a page at a time."""
    out: list[dict] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({"apiKey": key, "limit": PAGE, "offset": offset, "orderby": "created_at"})
        with urllib.request.urlopen(f"{API}/form/{form_id}/submissions?{query}", timeout=120) as r:
            page = json.load(r)
        content = page.get("content") or []
        out.extend(content)
        if len(content) < PAGE:
            return out
        offset += PAGE


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", action="append", help="a form id; default both forms")
    ap.add_argument("--key", help="the Jotform API key (else the environment or the env file)")
    ap.add_argument("--from-json", type=Path, help="import a saved fetch (a JSON list of submissions) instead of calling Jotform")
    ap.add_argument("--json-out", type=Path, help="write the raw fetch here, one file per form")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, write nothing")
    ap.add_argument("--database-url", default=settings.database_url)
    args = ap.parse_args()

    forms = args.form or ([NEW_FORM, OLD_FORM] if not args.from_json else [])
    if args.from_json and len(forms) != 1:
        print("--from-json needs exactly one --form", file=sys.stderr)
        return 2
    key = None
    if not args.from_json:
        key = find_key(args.key)
        if not key:
            print("no Jotform API key: --key, JOTFORM_API_KEY, or one of " + ", ".join(ENV_FILES), file=sys.stderr)
            return 2
    print(f"database: {args.database_url.split('@')[-1]}")

    engine = create_engine(args.database_url)
    exit_code = 0
    with Session(engine, autoflush=False) as db:
        for form_id in forms:
            if args.from_json:
                subs = json.loads(args.from_json.read_text(encoding="utf-8"))
                if isinstance(subs, dict):
                    subs = subs.get("content") or []
            else:
                try:
                    subs = fetch_all(form_id, key or "")
                except urllib.error.URLError as exc:
                    print(f"form {form_id}: Jotform unreachable: {exc}", file=sys.stderr)
                    exit_code = 1
                    continue
                if args.json_out:
                    args.json_out.mkdir(parents=True, exist_ok=True)
                    (args.json_out / f"jotform-{form_id}.json").write_text(json.dumps(subs), encoding="utf-8")
            print(f"form {form_id}: {len(subs)} submissions fetched")
            result = import_submissions(db, form_id, subs)
            print(
                f"  created {result['created']}, updated {result['updated']}, unchanged {result['unchanged']}, "
                f"skipped {result['skipped']}"
            )
            if result["jobs_added"]:
                print("  jobs added (inactive): " + ", ".join(result["jobs_added"]))
            if result["foremen_added"]:
                print("  foremen added (inactive): " + ", ".join(result["foremen_added"]))
            for line in result["errors"]:
                print("  error: " + line)
                exit_code = 1
        if args.dry_run:
            db.rollback()
            print("dry run — nothing written")
        else:
            db.commit()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
