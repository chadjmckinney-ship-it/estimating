"""
Who may do what — the one place that says it (sql/068).

Chad, 2026-09-07: "I want admin, senior estimator, estimator and user..
senior estimator can change pricing, user can only view. admin has access to
add, delete, users and full control." Each role includes the ones below it:

    user               reads everything; writes nothing
    estimator          the takeoff: projects and estimates, sections, pours,
                       groups, runs, types, levels, beams, the line sets'
                       switches and typed quantities, refreshes and recalcs;
                       deleting a row inside a takeoff (a pour, a run, a
                       type, a level, a group, a proposal line) only on an
                       estimate whose project lists them (app/ownership.py)
    senior_estimator   also the money: the three catalogs and suppliers,
                       company settings, a job's price sheet, rules, section
                       rates, quotes, a typed RATE on a line, the markup
                       (margin / contingency) on an estimate or a section,
                       and where a line is filed on the Summary (sql/088);
                       and deleting anything whole but an estimate or a
                       project — a section, a bid, a daily report, the
                       form's lists, a proposal, a catalog row (Chad,
                       2026-09-09: "estimators and lower.. no delete of
                       anything", records that is, "and only estimates they
                       are assigned to can they delete rows out of estimate
                       sections")
    management         senior_estimator by another name (sql/085): the same
                       rights, the same refusals; and management_notes on a
                       daily report is theirs and a senior's alone to see
    admin              also people (the estimators list and their passwords)
                       and deleting a whole estimate or project

    foreman            apart from the ladder (sql/084): files the daily report
                       a concrete order (sql/086) and a material order (sql/087),
                       reads under those three prefixes; nothing else

The activity feed (/api/audit) is senior_estimator and above, prices being
what it shows.

`needed(method, path, body_keys)` is the least role a request needs; the
`authorize` dependency in app/main.py asks it for every API route except
sign-in. A refusal is a 403 that names both roles, so the toast says why.
"""

from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import ownership
from app.auth import current_user
from app.db import get_db
from app.models.estimator import Estimator

ROLES = ("user", "estimator", "senior_estimator", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}
RANK["management"] = RANK["senior_estimator"]  # a peer, not a rung (sql/085)
LABEL = {
    "user": "a user",
    "estimator": "an estimator",
    "senior_estimator": "a senior estimator",
    "admin": "an admin",
    "management": "management",
    "foreman": "a foreman",
}
FIELD_ROLES = ("foreman",)
_FIELD_PREFIXES = ("/api/daily-reports", "/api/concrete-orders", "/api/material-orders")

_PRICING_PREFIXES = (
    "/api/mix-designs", "/api/concrete-suppliers", "/api/materials",
    "/api/equipment", "/api/system-settings",
    # The proposal's standing text carries the published day and hour rates (sql/080).
    "/api/proposal-library",
    # Where a priced line is filed on the estimate Summary (sql/088).
    "/api/cost-codes",
)
_JOB_PRICING = re.compile(r"/api/estimates/[^/]+/(prices|rules)(/.*)?")
_SECTION_PRICING = re.compile(r"/api/sections/[^/]+/(quotes|rates)(/.*)?")
_LINE_PATCH = re.compile(r"/api/sections/[^/]+/(labor|equipment)/lines/[^/]+")
_MARKUP_PATCH = re.compile(r"/api/(estimates|sections)/[^/]+")
_WHOLE_JOB = re.compile(r"/api/(estimates|projects)/[^/]+")
_MARKUP_KEYS = {"margin_pct", "contingency_pct"}


def needed(method: str, path: str, body_keys: set[str] | frozenset[str] = frozenset()) -> str:
    """The least role that may make this request."""
    method = method.upper()
    if path.startswith("/api/audit"):
        return "senior_estimator"  # who changed what, prices included (sql/069)
    if method in ("GET", "HEAD", "OPTIONS"):
        return "user"
    if path.startswith("/api/estimators"):
        return "admin"
    if method == "DELETE":
        if _WHOLE_JOB.fullmatch(path):
            return "admin"
        if ownership.ROW_DELETE.fullmatch(path):
            return "estimator"  # and only on an estimate they are on; authorize asks ownership
        return "senior_estimator"
    if method in ("PATCH", "POST") and path.startswith("/api/daily-reports") and "management_notes" in body_keys:
        return "senior_estimator"  # the note the field never sees (sql/085)
    if path.startswith(_PRICING_PREFIXES):
        return "senior_estimator"
    if _JOB_PRICING.fullmatch(path) or _SECTION_PRICING.fullmatch(path):
        return "senior_estimator"
    if method == "PATCH" and _LINE_PATCH.fullmatch(path) and "rate" in body_keys:
        return "senior_estimator"
    if method == "PATCH" and _MARKUP_PATCH.fullmatch(path) and body_keys & _MARKUP_KEYS:
        return "senior_estimator"
    return "estimator"


def field_allowed(method: str, path: str) -> bool:
    """A foreman (sql/084, 086): reads under the two field prefixes and files a report or an order. Nothing else."""
    if method.upper() in ("GET", "HEAD", "OPTIONS"):
        return path.startswith(_FIELD_PREFIXES)
    return method.upper() == "POST" and path.rstrip("/") in _FIELD_PREFIXES


def allowed(role: str, method: str, path: str, body_keys: set[str] | frozenset[str] = frozenset()) -> bool:
    if role in FIELD_ROLES:
        return field_allowed(method, path)
    return RANK.get(role, -1) >= RANK[needed(method, path, body_keys)]


async def _body_keys(request: Request) -> frozenset[str]:
    if request.method.upper() not in ("PATCH", "POST", "PUT"):
        return frozenset()
    if "json" not in (request.headers.get("content-type") or ""):
        return frozenset()
    try:
        data = await request.json()  # Starlette caches the body; the route reads it again fine
    except Exception:  # noqa: BLE001 — a body that is not JSON is the route's 422 to raise
        return frozenset()
    return frozenset(data.keys()) if isinstance(data, dict) else frozenset()


async def authorize(
    request: Request, user: Estimator = Depends(current_user), db: Session = Depends(get_db)
) -> Estimator:
    """Signed in, the role is enough for this request, and a takeoff row an estimator deletes is theirs."""
    keys = await _body_keys(request)
    path = request.url.path
    if user.role == "estimator" and request.method.upper() == "DELETE" and ownership.ROW_DELETE.fullmatch(path):
        project_id = ownership.project_of(db, path)
        if project_id is not None and not ownership.assigned(db, project_id, user.id):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"That row is on an estimate you are not assigned to; you are signed in as {user.full_name}, "
                    "an estimator. Ask a senior estimator, or to be added to the project."
                ),
            )
    if not allowed(user.role, request.method, request.url.path, keys):
        role_needed = needed(request.method, request.url.path, keys)
        raise HTTPException(
            status_code=403,
            detail=(
                f"That takes {LABEL[role_needed]} or above; you are signed in as "
                f"{user.full_name}, {LABEL.get(user.role, user.role)}."
            ),
        )
    return user
