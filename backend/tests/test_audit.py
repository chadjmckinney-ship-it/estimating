"""
Who changed what (sql/069, 2026-09-07).

The activity log records every write request — who, the route, the JSON they
sent with password fields blanked, the status — and every input table's
`updated_by` says who last touched the row. A recalc that rewrites calc_*
columns is not a person changing an input and leaves the stamp alone. The
log never breaks the request it records.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, text

from app import audit
from app.models.audit_log import AuditLog
from app.models.estimator import Estimator
from app.models.wall_run import WallRun
from tests import walls_fixture as wf

D = Decimal


def _person(db, username) -> Estimator:
    return db.scalars(select(Estimator).where(Estimator.username == username)).one()


def _newest(db) -> AuditLog:
    return db.scalars(select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc())).first()


def _count(db) -> int:
    return db.scalar(select(func.count()).select_from(AuditLog))


# ------------------------------------------------------------ the log --


def test_a_write_is_logged_with_who_what_and_status(db, as_role):
    c = as_role("estimator")
    r = c.post("/api/projects", json={"name": "logged"})
    assert r.status_code == 201, r.text
    row = _newest(db)
    assert (row.method, row.path, row.status) == ("POST", "/api/projects", 201)
    assert row.username == "test_estimator" and row.estimator_id == _person(db, "test_estimator").id
    assert row.body == {"name": "logged"}
    assert row.duration_ms is not None and row.duration_ms >= 0


def test_reads_are_not_logged(db, client):
    before = _count(db)
    assert client.get("/api/estimates").status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert _count(db) == before


def test_a_sign_in_is_logged_as_an_attempt_never_as_a_body(db, as_role):
    as_role("estimator")  # signs in
    row = db.scalars(
        select(AuditLog).where(AuditLog.path == "/api/auth/login").order_by(AuditLog.at.desc())
    ).first()
    assert row is not None and (row.status, row.username, row.body) == (200, "test_estimator", None)

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anon:
        anon.post("/api/auth/login", json={"username": "test_estimator", "password": "wrong"})
    row = _newest(db)
    assert (row.path, row.status, row.username, row.body, row.estimator_id) == (
        "/api/auth/login", 401, "test_estimator", None, None,
    )


def test_a_refused_write_is_logged_with_its_403(db, as_role):
    c = as_role("user")
    assert c.post("/api/projects", json={"name": "by a user"}).status_code == 403
    row = _newest(db)
    assert (row.method, row.path, row.status, row.username) == ("POST", "/api/projects", 403, "test_user")


def test_password_fields_are_blanked_however_deep():
    data = {"password": "x", "new_password": "y", "rows": [{"current_password": "z", "qty": 1}], "ok": 2}
    assert audit.redact(data) == {
        "password": "•••", "new_password": "•••", "rows": [{"current_password": "•••", "qty": 1}], "ok": 2,
    }


def test_a_password_change_is_logged_without_the_passwords(db, as_role):
    c = as_role("estimator")
    r = c.post("/api/auth/password", json={"current_password": "test-password", "new_password": "a-new-password"})
    assert r.status_code == 204, r.text
    row = _newest(db)
    assert row.path == "/api/auth/password" and row.body == {"current_password": "•••", "new_password": "•••"}


def test_a_logging_failure_never_breaks_the_request(db, as_role, monkeypatch):
    c = as_role("estimator")

    def boom(*a, **k):
        raise RuntimeError("no log for you")

    monkeypatch.setattr(audit, "record", boom)
    assert c.post("/api/projects", json={"name": "still saved"}).status_code == 201


# ---------------------------------------------------------- updated_by --


def test_a_takeoff_edit_stamps_who_did_it_and_only_that_row(db, estimate, as_role):
    section = wf.build(db, estimate)
    runs = db.scalars(select(WallRun).where(WallRun.section_id == section.id).order_by(WallRun.sort_order)).all()
    assert all(r.updated_by is None for r in runs), "fixtures are nobody's"
    c = as_role("estimator")
    r = c.patch(f"/api/wall-runs/{runs[0].id}", json={"length_ft": str(D(str(runs[0].length_ft)) + 1)})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert runs[0].updated_by == _person(db, "test_estimator").id
    assert all(r.updated_by is None for r in runs[1:]), "the other runs were only recalculated"


def test_a_recalc_does_not_claim_the_takeoff(db, estimate, as_role):
    section = wf.build(db, estimate)
    senior = as_role("senior_estimator")
    r = senior.patch("/api/system-settings/waste_concrete", json={"value": "0.07"})
    assert r.status_code == 200 and r.json()["recalculated"], r.text
    db.expire_all()
    runs = db.scalars(select(WallRun).where(WallRun.section_id == section.id)).all()
    assert runs and all(r.updated_by is None for r in runs)
    who = db.scalar(text("SELECT updated_by FROM system_settings WHERE key = 'waste_concrete'"))
    assert who == _person(db, "test_senior_estimator").id


def test_rules_and_section_rates_are_stamped_by_hand(db, estimate, as_role):
    section = wf.build(db, estimate)
    senior = as_role("senior_estimator")
    me = _person(db, "test_senior_estimator").id
    assert senior.put(f"/api/estimates/{estimate.id}/rules/waste_concrete", json={"value": "0.07"}).status_code == 200
    assert db.scalar(text("SELECT updated_by FROM estimate_rules WHERE estimate_id = :e AND key = 'waste_concrete'"),
                     {"e": str(estimate.id)}) == me
    assert senior.put(f"/api/sections/{section.id}/rates/labor_forming_sf", json={"value": "0.50"}).status_code == 200
    assert db.scalar(text("SELECT updated_by FROM section_rates WHERE section_id = :s AND key = 'labor_forming_sf'"),
                     {"s": str(section.id)}) == me


def test_a_new_section_and_its_seeded_rates_are_stamped(db, estimate, as_role):
    c = as_role("estimator")
    r = c.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "walls_footings", "name": "W", "unit": "LF"})
    assert r.status_code == 201, r.text
    me = _person(db, "test_estimator").id
    assert db.scalar(text("SELECT updated_by FROM estimate_sections WHERE id = :i"), {"i": r.json()["id"]}) == me
    seeded = db.execute(text("SELECT updated_by FROM section_rates WHERE section_id = :i"), {"i": r.json()["id"]}).all()
    assert seeded and all(row[0] == me for row in seeded)


# ------------------------------------------------------------ the feed --


def test_the_activity_feed_is_for_seniors_and_lists_newest_first(db, as_role):
    est = as_role("estimator")
    senior = as_role("senior_estimator")
    assert est.post("/api/projects", json={"name": "first"}).status_code == 201
    assert senior.post("/api/projects", json={"name": "second"}).status_code == 201

    assert est.get("/api/audit").status_code == 403
    r = senior.get("/api/audit?limit=5")
    assert r.status_code == 200, r.text
    feed = r.json()
    assert feed[0]["body"] == {"name": "second"} and feed[0]["username"] == "test_senior_estimator"
    assert {"at", "username", "method", "path", "status", "body", "duration_ms"} <= set(feed[0])

    r = senior.get("/api/audit?username=test_estimator&path=projects")
    assert r.status_code == 200 and all(e["username"] == "test_estimator" for e in r.json()) and r.json()
