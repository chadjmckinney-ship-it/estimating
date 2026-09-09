"""
Sign-in, sessions, and the four roles (sql/068, 2026-09-07).

Until now the API had no login and CORS was a wildcard with credentials
allowed: any website open in a browser while the server ran could drive the
API, and with -Lan anyone in the office could. Chad: "I want admin, senior
estimator, estimator and user.. senior estimator can change pricing, user can
only view. admin has access to add, delete, users and full control."

What this file pins: the session cookie and its flags; what ends a session
(sign-out, twelve idle hours, thirty days, a password reset, deactivation);
which role each kind of request needs, both as a table (app/policy.py) and
through the API; that the hash never leaves the server; and that a
cross-origin page gets no CORS answer at all.

Since sql/083 (2026-09-09, the day the app went public through Tailscale
Funnel): five wrong tries lock a name and twenty lock an address, fifteen
minutes each, and the API's own documentation needs a session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app import auth, policy
from app.models.estimator import Estimator
from app.models.login_failure import LoginFailure
from app.models.session import LoginSession
from tests import walls_fixture as wf


def _person(db, username):
    return db.scalars(select(Estimator).where(Estimator.username == username)).one()


def _sessions(db, username) -> int:
    return db.scalar(
        select(func.count()).select_from(LoginSession).where(LoginSession.estimator_id == _person(db, username).id)
    )


# ------------------------------------------------------------- sign-in --


def test_no_session_is_a_401_and_health_stays_open(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anon:
        r = anon.get("/api/estimates")
        assert r.status_code == 401 and "Sign in" in r.json()["detail"], r.text
        assert anon.get("/health").status_code == 200
        assert anon.get("/").status_code == 200  # the page itself is served; the API is the gate
        for path in ("/docs", "/redoc", "/openapi.json"):  # the API's own documentation too (sql/083)
            assert anon.get(path).status_code == 401, path


def test_the_api_documentation_is_for_the_signed_in(db, as_role):
    c = as_role("user")
    assert "/api/estimates" in c.get("/openapi.json").json()["paths"]
    assert "swagger" in c.get("/docs").text.lower()
    assert c.get("/redoc").status_code == 200


def test_sign_in_sets_a_locked_down_cookie(db, as_role):
    c = as_role("estimator")
    cookie = c.cookies.get(auth.COOKIE)
    assert cookie and len(cookie) >= 40
    me = c.get("/api/auth/me").json()
    assert (me["username"], me["role"]) == ("test_estimator", "estimator")
    assert "password_hash" not in me

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as fresh:
        r = fresh.post("/api/auth/login", json={"username": "test_estimator", "password": "test-password"})
        assert r.status_code == 200, r.text
        flags = r.headers["set-cookie"].lower()
        assert auth.COOKIE in flags and "httponly" in flags and "samesite=lax" in flags and "path=/" in flags
        assert "secure" not in flags  # plain http on the LAN; the flag follows the scheme


def test_over_https_the_cookie_is_secure(db, as_role):
    """run.ps1 serves https once backend/make_certs.py has run; the flag follows the scheme."""
    as_role("estimator")

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="https://testserver") as tls:
        r = tls.post("/api/auth/login", json={"username": "test_estimator", "password": "test-password"})
        assert r.status_code == 200, r.text
        assert "secure" in r.headers["set-cookie"].lower()


def test_wrong_unknown_inactive_and_passwordless_all_say_the_same_thing(db, as_role):
    as_role("estimator")  # creates test_estimator with a password
    nobody = Estimator(username="test_nopw", full_name="No Password", role="estimator")
    gone = Estimator(username="test_gone", full_name="Gone", role="estimator",
                     password_hash=auth.hash_password("test-password"), is_active=False)
    db.add_all([nobody, gone])
    db.flush()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        for body in (
            {"username": "test_estimator", "password": "wrong"},
            {"username": "nobody_here", "password": "test-password"},
            {"username": "test_gone", "password": "test-password"},
            {"username": "test_nopw", "password": "anything"},
        ):
            r = c.post("/api/auth/login", json=body)
            assert r.status_code == 401 and r.json()["detail"] == "Wrong username or password", (body, r.text)
        assert c.post("/api/auth/login", json={"username": "x", "password": "y", "extra": 1}).status_code == 422


def test_sign_out_ends_the_session(db, as_role):
    c = as_role("estimator")
    assert _sessions(db, "test_estimator") == 1
    assert c.post("/api/auth/logout").status_code == 204
    assert _sessions(db, "test_estimator") == 0
    assert c.get("/api/auth/me").status_code == 401


def test_twelve_idle_hours_or_thirty_days_end_a_session(db, as_role):
    c = as_role("estimator")
    row = db.scalars(select(LoginSession)).one()
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(hours=12, minutes=1)
    db.flush()
    assert c.get("/api/auth/me").status_code == 401
    assert _sessions(db, "test_estimator") == 0

    c = as_role("estimator")
    row = db.scalars(select(LoginSession)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    assert c.get("/api/estimates").status_code == 401


def test_a_request_touches_the_session_so_idle_counts_from_the_last_use(db, as_role):
    c = as_role("estimator")
    row = db.scalars(select(LoginSession)).one()
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(hours=11)
    db.flush()
    assert c.get("/api/auth/me").status_code == 200
    db.refresh(row)
    assert datetime.now(timezone.utc) - row.last_seen_at < timedelta(minutes=1)


# ------------------------------------------------------------- lockout --


def _failures(db, **where) -> int:
    stmt = select(func.count()).select_from(LoginFailure)
    for col, val in where.items():
        stmt = stmt.where(getattr(LoginFailure, col) == val)
    return db.scalar(stmt)


def test_five_wrong_tries_lock_the_name_for_fifteen_minutes(db, as_role):
    """sql/083: the right password does not get in while the name is locked, and a locked try is not counted."""
    as_role("estimator")

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        wrong = {"username": " Test_Estimator ", "password": "wrong"}  # as typed; counted lowercased and trimmed
        right = {"username": "test_estimator", "password": "test-password"}
        for _ in range(4):
            assert c.post("/api/auth/login", json=wrong).status_code == 401
        assert c.post("/api/auth/login", json=right).status_code == 200, "four is still a person mistyping"
        assert _failures(db, username="test_estimator") == 0, "a right sign-in clears the name's count"
        c.post("/api/auth/logout")

        for _ in range(5):
            assert c.post("/api/auth/login", json=wrong).status_code == 401
        assert _failures(db, username="test_estimator") == 5
        open_sessions = _sessions(db, "test_estimator")  # the fixture's own
        r = c.post("/api/auth/login", json=right)
        assert r.status_code == 429, r.text
        assert r.json()["detail"] == "Too many sign-in attempts for that username. Try again in 15 minutes."
        assert 0 < int(r.headers["retry-after"]) <= 15 * 60
        assert _failures(db, username="test_estimator") == 5, "a refused try is not another failure"
        assert _sessions(db, "test_estimator") == open_sessions, "and opened nothing"

        # Fifteen minutes on, the lock is gone: the right password signs in and the count starts over.
        for row in db.scalars(select(LoginFailure)).all():
            row.failed_at -= timedelta(minutes=15, seconds=1)
        db.flush()
        assert c.post("/api/auth/login", json=right).status_code == 200
        assert _failures(db, username="test_estimator") == 0

        # A name nobody has locks the same way, so the box says nothing about which names exist.
        for _ in range(5):
            assert c.post("/api/auth/login", json={"username": "nobody_here", "password": "x"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "NOBODY_HERE", "password": "x"}).status_code == 429


def test_twenty_failures_from_one_address_lock_the_address(db, as_role):
    """One name each, so no name is locked; the address is."""
    as_role("estimator")

    from fastapi.testclient import TestClient

    from app.main import app

    open_sessions = _sessions(db, "test_estimator")  # the fixture's own
    with TestClient(app) as c:
        for i in range(20):
            assert c.post("/api/auth/login", json={"username": f"guess_{i}", "password": "x"}).status_code == 401
        assert _failures(db, ip="testclient") == 20
        r = c.post("/api/auth/login", json={"username": "test_estimator", "password": "test-password"})
        assert r.status_code == 429 and "from this address" in r.json()["detail"], r.text
        assert _sessions(db, "test_estimator") == open_sessions


def test_failures_older_than_a_day_go_with_the_next_one(db, as_role):
    as_role("estimator")
    db.add(LoginFailure(username="stale", ip="testclient",
                        failed_at=datetime.now(timezone.utc) - timedelta(days=1, minutes=1)))
    db.flush()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "fresh", "password": "x"}).status_code == 401
    assert _failures(db, username="stale") == 0 and _failures(db, username="fresh") == 1


# ----------------------------------------------------------- passwords --


def test_changing_my_password_signs_out_my_other_sessions(db, as_role):
    here = as_role("estimator")
    there = as_role("estimator")  # the same person, a second browser
    assert _sessions(db, "test_estimator") == 2
    r = here.post("/api/auth/password", json={"current_password": "wrong", "new_password": "a-new-password"})
    assert r.status_code == 400
    r = here.post("/api/auth/password", json={"current_password": "test-password", "new_password": "a-new-password"})
    assert r.status_code == 204, r.text
    assert here.get("/api/auth/me").status_code == 200, "this session stays"
    assert there.get("/api/auth/me").status_code == 401, "the other one ended"
    assert auth.verify_password("a-new-password", _person(db, "test_estimator").password_hash)
    assert not auth.verify_password("test-password", _person(db, "test_estimator").password_hash)
    r = here.post("/api/auth/password", json={"current_password": "a-new-password", "new_password": "short"})
    assert r.status_code == 422


def test_an_admin_resets_a_password_and_ends_that_persons_sessions(db, as_role):
    them = as_role("estimator")
    admin = as_role("admin")
    senior = as_role("senior_estimator")
    pid = str(_person(db, "test_estimator").id)
    assert senior.post(f"/api/estimators/{pid}/password", json={"password": "reset-by-senior"}).status_code == 403
    assert admin.post(f"/api/estimators/{pid}/password", json={"password": "reset-by-admin"}).status_code == 204
    assert them.get("/api/auth/me").status_code == 401
    assert auth.verify_password("reset-by-admin", _person(db, "test_estimator").password_hash)


def test_deactivating_a_person_signs_them_out(db, as_role):
    them = as_role("estimator")
    admin = as_role("admin")
    pid = str(_person(db, "test_estimator").id)
    assert admin.delete(f"/api/estimators/{pid}").status_code == 204
    assert them.get("/api/auth/me").status_code == 401


def test_the_hash_never_leaves_the_server(db, client):
    pid = str(_person(db, "test_admin").id)
    for payload in (client.get(f"/api/estimators/{pid}").json(), client.get("/api/estimators").json()[0]):
        assert "password_hash" not in payload


def test_the_production_work_factor_fits_in_memory(monkeypatch):
    """The suite runs at a light N; the real one is 2**15, which the default scrypt ceiling refused."""
    monkeypatch.setattr(auth, "_N", 2**15)
    h = auth.hash_password("at full strength")
    assert h.startswith("scrypt$32768$8$1$") and auth.verify_password("at full strength", h)


def test_hashes_are_salted_and_verify_across_work_factors():
    a, b = auth.hash_password("same"), auth.hash_password("same")
    assert a != b and a.startswith("scrypt$") and b.startswith("scrypt$")
    assert auth.verify_password("same", a) and auth.verify_password("same", b)
    assert not auth.verify_password("other", a)
    assert not auth.verify_password("same", None) and not auth.verify_password("same", "garbage")


# --------------------------------------------------------------- roles --


@pytest.mark.parametrize("method,path,keys,role", [
    ("GET", "/api/system-settings", set(), "user"),
    ("GET", "/api/estimators", set(), "user"),
    ("POST", "/api/projects", set(), "estimator"),
    ("PUT", "/api/wall-runs/bulk", set(), "estimator"),
    ("POST", "/api/sections/x/recalc", set(), "estimator"),
    ("PATCH", "/api/sections/x/labor/lines/tie_steel", {"enabled"}, "estimator"),
    ("PATCH", "/api/sections/x/labor/lines/tie_steel", {"rate", "mark_manual"}, "senior_estimator"),
    ("PATCH", "/api/sections/x/equipment/lines/pump", {"days_qty"}, "estimator"),
    ("PATCH", "/api/sections/x/equipment/lines/pump", {"rate"}, "senior_estimator"),
    ("PATCH", "/api/sections/x", {"name"}, "estimator"),
    ("PATCH", "/api/sections/x", {"margin_pct"}, "senior_estimator"),
    ("PATCH", "/api/estimates/x", {"contingency_pct"}, "senior_estimator"),
    ("PUT", "/api/sections/x/forming-materials/form-percent", set(), "estimator"),
    ("POST", "/api/materials", set(), "senior_estimator"),
    ("PATCH", "/api/mix-designs/3", set(), "senior_estimator"),
    ("PATCH", "/api/system-settings/waste_concrete", set(), "senior_estimator"),
    ("POST", "/api/system-settings/recalc-all", set(), "senior_estimator"),
    ("POST", "/api/estimates/x/prices/pull", set(), "senior_estimator"),
    ("PUT", "/api/estimates/x/rules/waste_concrete", set(), "senior_estimator"),
    ("PUT", "/api/sections/x/quotes/rebar", set(), "senior_estimator"),
    ("PUT", "/api/sections/x/rates/labor_forming_sf", set(), "senior_estimator"),
    ("DELETE", "/api/sections/x", set(), "estimator"),
    ("DELETE", "/api/estimates/x", set(), "admin"),
    ("DELETE", "/api/projects/x", set(), "admin"),
    ("POST", "/api/estimators", set(), "admin"),
    ("POST", "/api/estimators/x/password", set(), "admin"),
    # The proposal (sql/080): the form is the takeoff's to make; the company's standing text is a senior's.
    ("POST", "/api/proposals", set(), "estimator"),
    ("PUT", "/api/proposal-sections/x/lines/bulk", set(), "estimator"),
    ("GET", "/api/proposals/x/xlsx", set(), "user"),
    ("PUT", "/api/proposal-library/labor_rates", set(), "senior_estimator"),
    # Daily reports (sql/084): the office files, edits and keeps the lists; the foreman role is a
    # branch off the ladder, pinned in test_daily_reports.py.
    ("GET", "/api/daily-reports", set(), "user"),
    ("POST", "/api/daily-reports", set(), "estimator"),
    ("PATCH", "/api/daily-reports/x", {"delays"}, "estimator"),
    ("POST", "/api/daily-reports/jobs", set(), "estimator"),
])
def test_the_policy_table(method, path, keys, role):
    assert policy.needed(method, path, keys) == role
    assert policy.allowed(role, method, path, keys)
    below = policy.ROLES[policy.RANK[role] - 1] if policy.RANK[role] else None
    if below:
        assert not policy.allowed(below, method, path, keys)


def test_the_roles_through_the_api(db, estimate, as_role):
    section = wf.build(db, estimate)
    line = as_role("admin").get(f"/api/sections/{section.id}/labor").json()["lines"][0]["code"]
    user, est, senior, admin = (as_role(r) for r in ("user", "estimator", "senior_estimator", "admin"))

    for c in (user, est, senior, admin):
        assert c.get(f"/api/sections/{section.id}").status_code == 200

    r = user.post("/api/projects", json={"name": "by a user"})
    assert r.status_code == 403 and "an estimator or above" in r.json()["detail"], r.text
    assert est.post("/api/projects", json={"name": "by an estimator"}).status_code == 201

    assert est.patch(f"/api/sections/{section.id}/labor/lines/{line}", json={"enabled": False}).status_code == 200
    r = est.patch(f"/api/sections/{section.id}/labor/lines/{line}", json={"rate": "1.25"})
    assert r.status_code == 403 and "senior estimator" in r.json()["detail"], r.text
    assert senior.patch(f"/api/sections/{section.id}/labor/lines/{line}", json={"rate": "1.25"}).status_code == 200

    assert est.patch(f"/api/sections/{section.id}", json={"name": "renamed"}).status_code == 200
    assert est.patch(f"/api/sections/{section.id}", json={"margin_pct": "0.25"}).status_code == 403
    assert senior.patch(f"/api/sections/{section.id}", json={"margin_pct": "0.25"}).status_code == 200

    body = {"name": "TEST ROLE MATERIAL", "category": "lumber", "unit": "EA", "unit_cost": "1"}
    assert est.post("/api/materials", json=body).status_code == 403
    assert senior.post("/api/materials", json=body).status_code == 201

    assert est.put(f"/api/estimates/{estimate.id}/rules/waste_concrete", json={"value": "0.07"}).status_code == 403
    assert senior.put(f"/api/estimates/{estimate.id}/rules/waste_concrete", json={"value": "0.07"}).status_code == 200

    person = {"username": "test_new_person", "full_name": "New Person", "role": "user"}
    assert senior.post("/api/estimators", json=person).status_code == 403
    assert admin.post("/api/estimators", json=person).status_code == 201

    empty = admin.post("/api/estimates", json={"project_id": str(estimate.project_id), "name": "to delete"}).json()
    assert senior.delete(f"/api/estimates/{empty['id']}").status_code == 403
    assert admin.delete(f"/api/estimates/{empty['id']}").status_code == 204


def test_a_new_project_is_stamped_with_who_made_it(db, as_role):
    c = as_role("estimator")
    r = c.post("/api/projects", json={"name": "stamped"})
    assert r.status_code == 201, r.text
    assert r.json()["created_by"] == str(_person(db, "test_estimator").id)


def test_the_four_roles_are_the_only_ones_the_database_takes(db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("INSERT INTO estimators (username, full_name, role) VALUES ('test_x', 'X', 'viewer')"))


# ---------------------------------------------------------------- CORS --


def test_a_cross_origin_page_gets_no_cors_answer(client):
    r = client.get("/api/bar-sizes", headers={"Origin": "https://evil.test"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
    r = client.options("/api/bar-sizes", headers={
        "Origin": "https://evil.test", "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
