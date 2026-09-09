"""
The 8:05 email of open bids, read from the app's bid list (sql/082) instead of Notion.

    .venv/bin/python backend/email_current_bids.py              # send
    .venv/bin/python backend/email_current_bids.py --dry-run    # print the message instead

Until 2026-09-09 ~/gmail-bid-notion-sync/email_current_bids.py read the Notion
database; this is the same message from bid_requests — the open bids (not
started, in progress) as overdue, due today, due in the next seven days, and
later or undated — sent through ~/daily-status-report/outlook_mail.py, the
Microsoft Graph sender both morning emails use, to REPORT_TO_EMAIL unless
BIDS_EMAIL_TO or --to names others. The unit on the box is
current-bids-email.service, now pointed here.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.bid_request import BidRequest  # noqa: E402
from app.models.estimator import Estimator  # noqa: E402

MAIL_DIR = Path(os.environ.get("ORDERS_MAIL_DIR", "~/daily-status-report")).expanduser()
OPEN_STATUSES = ("not_started", "in_progress")
STATUS_LABEL = {
    "not_started": "Not started", "in_progress": "In progress", "submitted": "Submitted",
    "awarded": "Awarded", "canceled": "Canceled",
}
APP_URL = os.environ.get("ESTIMATING_APP_URL", "https://estimating.tail5fb2cd.ts.net/#bids")


def open_bids(db: Session) -> list[dict]:
    """The open bids with their people, soonest due first, undated last."""
    people = {e.id: e.full_name for e in db.scalars(select(Estimator)).all()}
    rows = db.scalars(select(BidRequest).where(BidRequest.status.in_(OPEN_STATUSES))).unique().all()
    out = []
    for b in rows:
        out.append({
            "name": b.name, "status": b.status, "bid_due": b.bid_due, "bid_due_time": b.bid_due_time,
            "gc": b.gc or "", "project_types": list(b.project_types or []), "location": b.location or "",
            "estimators": [people[l.estimator_id] for l in (b.estimator_links or []) if l.estimator_id in people],
            "notes": (b.notes or "")[:200], "plans_url": b.plans_url or "",
        })
    out.sort(key=lambda r: (r["bid_due"] is None, r["bid_due"] or date.max, r["bid_due_time"] or datetime.min.time(), r["name"].lower()))
    return out


def _due_label(r: dict, today: date) -> str:
    d = r["bid_due"]
    if d is None:
        return "no due date"
    hour = f" {r['bid_due_time'].strftime('%I:%M %p').lstrip('0')}" if r["bid_due_time"] else ""
    if d < today:
        return f"{d.isoformat()}{hour}  OVERDUE ({(today - d).days}d)"
    if d == today:
        return f"{d.isoformat()}{hour}  DUE TODAY"
    return f"{d.isoformat()}{hour}  (in {(d - today).days}d)"


def format_report(rows: list[dict], today: date | None = None) -> tuple[str, str]:
    """(subject, body) in the style of the Notion-era email."""
    today = today or date.today()
    overdue = [r for r in rows if r["bid_due"] and r["bid_due"] < today]
    due_today = [r for r in rows if r["bid_due"] == today]
    due_7 = [r for r in rows if r["bid_due"] and today < r["bid_due"] <= today + timedelta(days=7)]
    later = [r for r in rows if r["bid_due"] is None or r["bid_due"] > today + timedelta(days=7)]

    subject = f"Current bids — {today.isoformat()}: {len(rows)} open"
    if overdue:
        subject += f", {len(overdue)} overdue"
    if due_today:
        subject += f", {len(due_today)} due today"
    if due_7:
        subject += f", {len(due_7)} due this week"

    lines = [
        f"Current Bid Requests — {today.isoformat()}",
        f"Open statuses: {', '.join(STATUS_LABEL[s] for s in OPEN_STATUSES)}",
        f"Total open: {len(rows)}",
        f"  Overdue: {len(overdue)}  |  Due today: {len(due_today)}  |  Next 7 days: {len(due_7)}  |  Later/undated: {len(later)}",
        "",
    ]

    def section(title: str, items: list[dict]) -> None:
        lines.append(f"=== {title} ({len(items)}) ===")
        if not items:
            lines.append("  (none)")
            lines.append("")
            return
        for i, r in enumerate(items, 1):
            lines.append(f"{i}. {r['name']}")
            lines.append(f"   Due:    {_due_label(r, today)}")
            lines.append(f"   Status: {STATUS_LABEL.get(r['status'], r['status'])}")
            if r["gc"]:
                lines.append(f"   GC:     {r['gc']}")
            if r["project_types"]:
                lines.append(f"   Type:   {', '.join(r['project_types'])}")
            if r["location"]:
                lines.append(f"   Loc:    {r['location']}")
            if r["estimators"]:
                lines.append(f"   Est:    {', '.join(r['estimators'])}")
            if r["plans_url"]:
                lines.append(f"   Plans:  {r['plans_url']}")
            lines.append("")
        lines.append("")

    section("OVERDUE", overdue)
    section("DUE TODAY", due_today)
    section("DUE IN NEXT 7 DAYS", due_7)
    section("LATER / NO DUE DATE", later)
    lines.append(f"The list: {APP_URL}")
    lines.append(f"Generated {datetime.now().astimezone():%Y-%m-%d %H:%M %Z}")
    lines.append("Source: the estimating app on the office box (bid_requests).")
    return subject, "\n".join(lines).rstrip() + "\n"


def send(subject: str, body: str, to: str | None) -> tuple[bool, str]:
    sys.path.insert(0, str(MAIL_DIR))
    try:
        import outlook_mail  # noqa: PLC0415 — the box's module, not the app's
    except ImportError as exc:
        return False, f"outlook_mail not importable from {MAIL_DIR}: {exc}"
    outlook_mail.load_env()
    addresses = [a.strip() for a in (to or os.environ.get("BIDS_EMAIL_TO", "")).split(",") if a.strip()]
    if not addresses:
        return outlook_mail.send_report_email(subject, body)
    problems = []
    for addr in addresses:
        os.environ["REPORT_TO_EMAIL"] = addr
        ok, msg = outlook_mail.send_report_email(subject, body)
        if not ok:
            problems.append(f"{addr}: {msg}")
    return (not problems), "; ".join(problems) if problems else f"sent to {', '.join(addresses)}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", help="addresses, commas between; else BIDS_EMAIL_TO, else REPORT_TO_EMAIL")
    ap.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    ap.add_argument("--database-url", default=settings.database_url)
    args = ap.parse_args()

    engine = create_engine(args.database_url)
    with Session(engine, autoflush=False) as db:
        subject, body = format_report(open_bids(db))
    if args.dry_run:
        print(f"Subject: {subject}\n")
        print(body)
        return 0
    ok, msg = send(subject, body, args.to)
    print(("sent: " if ok else "NOT sent: ") + (msg or subject))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
