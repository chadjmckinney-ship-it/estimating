"""
Email the next seven days of concrete orders (sql/086), every morning.

    .venv/bin/python backend/email_concrete_orders.py                  # send
    .venv/bin/python backend/email_concrete_orders.py --dry-run        # print the message instead
    .venv/bin/python backend/email_concrete_orders.py --days 10 --to a@x.com,b@y.com

Chad, 2026-09-09: "is it possible to have it send an email daily with a
list of concrete orders for the next 7 days?" — on the proposal, "build it".

Reads the app's database and sends through ~/daily-status-report/
outlook_mail.py, the Microsoft Graph sender the morning bid email uses (its
token from a one-time device login, its .env for the tenant and the
addresses). The message goes to REPORT_TO_EMAIL unless ORDERS_EMAIL_TO in
that .env, or --to, names others (commas between them; one message each). A
morning with nothing ordered still gets the message, saying so, unless
--skip-empty. On the box this runs as concrete-orders-email.timer at 06:30.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.concrete_order import ConcreteOrder  # noqa: E402
from app.models.material_order import KIND_LABELS, MaterialOrder  # noqa: E402

MAIL_DIR = Path(os.environ.get("ORDERS_MAIL_DIR", "~/daily-status-report")).expanduser()


def clock(t) -> str:
    """07:00 → 7:00 AM."""
    if t is None:
        return ""
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'PM' if t.hour >= 12 else 'AM'}"


def orders_in(db: Session, start: date, days: int) -> list[ConcreteOrder]:
    """The orders whose pour falls in the window, canceled ones left out, soonest first."""
    end = start + timedelta(days=days)
    stmt = (
        select(ConcreteOrder)
        .where(ConcreteOrder.pour_date >= start, ConcreteOrder.pour_date < end, ConcreteOrder.status != "canceled")
        .order_by(ConcreteOrder.pour_date, ConcreteOrder.pour_time.nulls_last(), ConcreteOrder.created_at)
    )
    return list(db.scalars(stmt).unique().all())


def materials_in(db: Session, start: date, days: int) -> list[MaterialOrder]:
    """The material orders needed on site in the window, delivered and canceled ones left out (sql/087)."""
    end = start + timedelta(days=days)
    stmt = (
        select(MaterialOrder)
        .where(
            MaterialOrder.needed_by >= start, MaterialOrder.needed_by < end,
            MaterialOrder.status.not_in(("delivered", "canceled")),
        )
        .order_by(MaterialOrder.needed_by, MaterialOrder.created_at)
    )
    return list(db.scalars(stmt).unique().all())


def _qty(m) -> str:
    if m.quantity is None:
        return ""
    d = Decimal(m.quantity)
    q = f"{d:,.2f}".rstrip("0").rstrip(".")
    return f"{q} {m.unit or ''}".strip()


def _yards(v) -> str:
    d = Decimal(v or 0)
    return f"{d:,.1f}" if d != d.to_integral() else f"{int(d):,}"


def _materials_section(materials: list, start: date, days: int) -> list[str]:
    end = start + timedelta(days=days - 1)
    lines = [f"=== MATERIALS DUE ON SITE {start:%b %d} to {end:%b %d} ({len(materials)}) ==="]
    if not materials:
        lines += ["  (none)", ""]
        return lines
    for i, m in enumerate(materials, 1):
        job = m.job.name if getattr(m, "job", None) is not None else str(getattr(m, "job_name", ""))
        kind = KIND_LABELS.get(m.kind, (m.kind, ""))[0]
        when = "TODAY" if m.needed_by == start else "TOMORROW" if m.needed_by == start + timedelta(days=1) else ""
        lines.append(f"{i}. {m.needed_by:%a %b %d}{' ' + when if when else ''}  {kind} — {job}")
        lines.append(f"   What:       {m.description}{'  (' + _qty(m) + ')' if _qty(m) else ''}")
        lines.append(f"   Supplier:   {m.supplier}{'  #' + m.order_number if m.order_number else ''}")
        lines.append(f"   Ordered by: {m.ordered_by or '—'} on {m.ordered_on:%b %d}   Status: {m.status}")
        if m.notes:
            lines.append(f"   Notes:      {m.notes}")
        lines.append("")
    return lines


def format_report(orders: list, start: date, days: int, materials: list | None = None) -> tuple[str, str]:
    """(subject, body). Plain text, a day at a time, in the house style of the bid email; the deliveries after."""
    materials = list(materials or [])
    end = start + timedelta(days=days - 1)
    total = sum((Decimal(o.yards or 0) for o in orders), Decimal(0))
    span = f"{start:%a %b %d} to {end:%a %b %d}"
    deliveries = f", {len(materials)} deliver{'y' if len(materials) == 1 else 'ies'}" if materials else ""
    if not orders and not materials:
        subject = f"Concrete orders: nothing ordered for the next {days} days"
        body = "\n".join([
            f"Concrete orders — {span}",
            "",
            f"No pours ordered and no deliveries due for the next {days} days.",
            "",
            f"Generated {datetime.now().astimezone():%Y-%m-%d %H:%M %Z}",
            "Source: the estimating app on the office box (concrete_orders, material_orders).",
        ]) + "\n"
        return subject, body

    if orders:
        subject = f"Concrete orders, next {days} days: {len(orders)} pour{'' if len(orders) == 1 else 's'}, {_yards(total)} yd{deliveries}"
    else:
        subject = f"Concrete orders, next {days} days: no pours{deliveries}"
    lines = [
        f"Concrete orders — {span}",
        f"{len(orders)} pour{'' if len(orders) == 1 else 's'} · {_yards(total)} yards ordered" + (f" · {len(materials)} deliver{'y' if len(materials) == 1 else 'ies'} due" if materials else ""),
        "",
    ]
    if not orders:
        lines += [f"No pours ordered for the next {days} days.", ""]
    by_day: dict[date, list] = {}
    for o in orders:
        by_day.setdefault(o.pour_date, []).append(o)
    n = 0
    for day in sorted(by_day):
        items = by_day[day]
        day_yards = sum((Decimal(o.yards or 0) for o in items), Decimal(0))
        label = "TODAY" if day == start else "TOMORROW" if day == start + timedelta(days=1) else ""
        lines.append(f"=== {day:%A %b %d}{' — ' + label if label else ''} ({len(items)}, {_yards(day_yards)} yd) ===")
        for o in items:
            n += 1
            when = clock(o.pour_time)
            job = o.job.name if getattr(o, "job", None) is not None else str(getattr(o, "job_name", ""))
            lines.append(f"{n}. {when + '  ' if when else ''}{job} — {_yards(o.yards)} yd {o.supplier}{' · ' + o.mix if o.mix else ''}")
            if o.order_number:
                lines.append(f"   Order #:    {o.order_number}")
            lines.append(f"   Ordered by: {o.ordered_by or '—'} on {o.ordered_on:%b %d}")
            lines.append(f"   Status:     {o.status}")
            if o.notes:
                lines.append(f"   Notes:      {o.notes}")
            lines.append("")
        lines.append("")
    if materials:
        lines += _materials_section(materials, start, days)
        lines.append("")
    lines.append(f"Generated {datetime.now().astimezone():%Y-%m-%d %H:%M %Z}")
    lines.append("Source: the estimating app on the office box (concrete_orders, material_orders).")
    return subject, "\n".join(lines).rstrip() + "\n"


def send(subject: str, body: str, to: str | None) -> tuple[bool, str]:
    """Through the box's Outlook sender; one message per address when several are named."""
    sys.path.insert(0, str(MAIL_DIR))
    try:
        import outlook_mail  # noqa: PLC0415 — the box's module, not the app's
    except ImportError as exc:
        return False, f"outlook_mail not importable from {MAIL_DIR}: {exc}"
    outlook_mail.load_env()
    addresses = [a.strip() for a in (to or os.environ.get("ORDERS_EMAIL_TO", "")).split(",") if a.strip()]
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
    ap.add_argument("--days", type=int, default=7, help="the window, today included (default 7)")
    ap.add_argument("--to", help="addresses, commas between; else ORDERS_EMAIL_TO, else the bid email's REPORT_TO_EMAIL")
    ap.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    ap.add_argument("--skip-empty", action="store_true", help="send nothing when nothing is ordered")
    ap.add_argument("--database-url", default=settings.database_url)
    args = ap.parse_args()

    start = date.today()
    engine = create_engine(args.database_url)
    with Session(engine, autoflush=False) as db:
        orders = orders_in(db, start, args.days)
        materials = materials_in(db, start, args.days)
        subject, body = format_report(orders, start, args.days, materials)
    if args.dry_run:
        print(f"Subject: {subject}\n")
        print(body)
        return 0
    if not orders and not materials and args.skip_empty:
        print("nothing ordered; not sent")
        return 0
    ok, msg = send(subject, body, args.to)
    print(("sent: " if ok else "NOT sent: ") + (msg or subject))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
