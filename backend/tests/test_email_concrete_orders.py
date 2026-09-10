"""
The morning concrete-orders email (2026-09-09; Chad: "send an email daily
with a list of concrete orders for the next 7 days?").

Pinned here: the window (today through six days on, canceled left out,
soonest first); the message a day at a time with the totals, TODAY and
TOMORROW marked, the order number, who ordered and when, notes; and the
message for a week with nothing ordered.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.concrete_order import ConcreteOrder
from app.models.daily_report import FieldJob
from app.models.material_order import MaterialOrder
from email_concrete_orders import clock, format_report, materials_in, orders_in


def _job(db, name: str) -> FieldJob:
    return db.scalars(select(FieldJob).where(FieldJob.name == name)).one()


def test_the_window_and_the_message(db):
    today = date(2026, 9, 9)
    nw, md = _job(db, "NORTHWEST VILLAGE"), _job(db, "MANHEIM DALLAS")
    rows = [
        ConcreteOrder(ordered_on=today, job_id=nw.id, supplier="Cowtown", pour_date=today, pour_time=time(7, 0),
                      yards=Decimal("42.5"), mix="4000-3A", order_number="CT-88231", ordered_by="Jorge",
                      notes="Pump on site by 6.", status="confirmed"),
        ConcreteOrder(ordered_on=today, job_id=md.id, supplier="SRM", pour_date=today + timedelta(days=1),
                      yards=Decimal("18"), status="ordered", ordered_by="Pedro"),
        ConcreteOrder(ordered_on=today, job_id=nw.id, supplier="SRM", pour_date=today + timedelta(days=6),
                      pour_time=time(13, 30), yards=Decimal("100"), status="ordered", ordered_by="Chad"),
        # Out of the window, or canceled: not in the email.
        ConcreteOrder(ordered_on=today, job_id=nw.id, supplier="Cowtown", pour_date=today + timedelta(days=7),
                      yards=Decimal("9"), status="ordered"),
        ConcreteOrder(ordered_on=today, job_id=nw.id, supplier="Cowtown", pour_date=today - timedelta(days=1),
                      yards=Decimal("9"), status="poured"),
        ConcreteOrder(ordered_on=today, job_id=nw.id, supplier="Cowtown", pour_date=today + timedelta(days=2),
                      yards=Decimal("9"), status="canceled"),
    ]
    db.add_all(rows)
    db.flush()

    orders = orders_in(db, today, 7)
    assert [(o.pour_date, o.supplier) for o in orders] == [
        (today, "Cowtown"), (today + timedelta(days=1), "SRM"), (today + timedelta(days=6), "SRM"),
    ]
    subject, body = format_report(orders, today, 7)
    assert subject == "Concrete orders, next 7 days: 3 pours, 160.5 yd"
    assert body.startswith("Concrete orders — Wed Sep 09 to Tue Sep 15\n3 pours · 160.5 yards ordered\n")
    assert "=== Wednesday Sep 09 — TODAY (1, 42.5 yd) ===" in body
    assert "1. 7:00 AM  NORTHWEST VILLAGE — 42.5 yd Cowtown · 4000-3A" in body
    assert "   Order #:    CT-88231" in body and "   Ordered by: Jorge on Sep 09" in body
    assert "   Status:     confirmed" in body and "   Notes:      Pump on site by 6." in body
    assert "=== Thursday Sep 10 — TOMORROW (1, 18 yd) ===" in body and "2. MANHEIM DALLAS — 18 yd SRM\n" in body
    assert "=== Tuesday Sep 15 (1, 100 yd) ===" in body and "3. 1:30 PM  NORTHWEST VILLAGE — 100 yd SRM" in body
    assert "canceled" not in body and body.count("Order #") == 1
    assert clock(time(0, 5)) == "12:05 AM" and clock(time(12, 0)) == "12:00 PM" and clock(None) == ""


def test_a_week_with_nothing_ordered_still_says_so(db):
    today = date(2026, 9, 9)
    assert orders_in(db, today, 7) == [] and materials_in(db, today, 7) == []
    subject, body = format_report([], today, 7)
    assert subject == "Concrete orders: nothing ordered for the next 7 days"
    assert "No pours ordered and no deliveries due for the next 7 days." in body and "Wed Sep 09 to Tue Sep 15" in body


def test_the_deliveries_due_join_the_message(db):
    """sql/087: rebar and post-tension needed on site in the window, delivered and canceled left out."""
    today = date(2026, 9, 9)
    nw = _job(db, "NORTHWEST VILLAGE")
    db.add_all([
        MaterialOrder(kind="rebar", ordered_on=today, job_id=nw.id, supplier="CMC", description="#5 x 20' per S-3",
                      quantity=Decimal("12.5"), unit="TON", needed_by=today + timedelta(days=1), order_number="CMC-4471",
                      ordered_by="Chad", status="confirmed", notes="East gate."),
        MaterialOrder(kind="post_tension", ordered_on=today, job_id=nw.id, supplier="Suncoast", description="PT per S-5",
                      needed_by=today, status="ordered", ordered_by="Chad"),
        MaterialOrder(kind="rebar", ordered_on=today, job_id=nw.id, supplier="CMC", description="delivered already",
                      needed_by=today + timedelta(days=2), status="delivered", delivered_on=today),
        MaterialOrder(kind="other", ordered_on=today, job_id=nw.id, supplier="Whitecap", description="too late",
                      needed_by=today + timedelta(days=7), status="ordered"),
    ])
    db.flush()
    materials = materials_in(db, today, 7)
    assert [m.description for m in materials] == ["PT per S-5", "#5 x 20' per S-3"]
    subject, body = format_report([], today, 7, materials)
    assert subject == "Concrete orders, next 7 days: no pours, 2 deliveries"
    assert "0 pours · 0 yards ordered · 2 deliveries due" in body and "No pours ordered for the next 7 days." in body
    assert "=== MATERIALS DUE ON SITE Sep 09 to Sep 15 (2) ===" in body
    assert "1. Wed Sep 09 TODAY  Post-tension — NORTHWEST VILLAGE\n   What:       PT per S-5\n   Supplier:   Suncoast\n" in body
    assert "2. Thu Sep 10 TOMORROW  Rebar — NORTHWEST VILLAGE\n   What:       #5 x 20' per S-3  (12.5 TON)\n   Supplier:   CMC  #CMC-4471\n   Ordered by: Chad on Sep 09   Status: confirmed\n   Notes:      East gate.\n" in body
    assert "delivered already" not in body and "too late" not in body
