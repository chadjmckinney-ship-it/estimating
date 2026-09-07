"""
Who may do what — the one place that says it (sql/068).

Chad, 2026-09-07: "I want admin, senior estimator, estimator and user..
senior estimator can change pricing, user can only view. admin has access to
add, delete, users and full control." Each role includes the ones below it:

    user               reads everything; writes nothing
    estimator          the takeoff: projects and estimates, sections, pours,
                       groups, runs, types, levels, beams, the line sets'
                       switches and typed quantities, refreshes and recalcs
    senior_estimator   also the money: the three catalogs and suppliers,
                       company settings, a job's price sheet, rules, section
                       rates, quotes, a typed RATE on a line, and the markup
                       (margin / contingency) on an estimate or a section
    admin              also people (the estimators list and their passwords)
                       and deleting a whole estimate or project

The activity feed (/api/audit) is senior_estimator and above, prices being
what it shows.

`needed(method, path, body_keys)` is the least role a request needs; the
`authorize` dependency in app/main.py asks it for every API route except
sign-in. A refusal is a 403 that names both roles, so the toast says why.
"""

from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Request

from app.auth import current_user
from app.models.estimator import Estimator

ROLES = ("user", "estimator", "senior_estimator", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}
LABEL = {
    "user": "a user",
    "estimator": "an estimator",
    "senior_estimator": "a senior estimator",
    "admin": "an admin",
}

_PRICING_PREFIXES = (
    "/api/mix-designs", "/api/concrete-suppliers", "/api/materials",
    "/api/equipment", "/api/system-settings",
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
    if method == "DELETE" and _WHOLE_JOB.fullmatch(path):
        return "admin"
    if path.startswith(_PRICING_PREFIXES):
        return "senior_estimator"
    if _JOB_PRICING.fullmatch(path) or _SECTION_PRICING.fullmatch(path):
        return "senior_estimator"
    if method == "PATCH" and _LINE_PATCH.fullmatch(path) and "rate" in body_keys:
        return "senior_estimator"
    if method == "PATCH" and _MARKUP_PATCH.fullmatch(path) and body_keys & _MARKUP_KEYS:
        return "senior_estimator"
    return "estimator"


def allowed(role: str, method: str, path: str, body_keys: set[str] | frozenset[str] = frozenset()) -> bool:
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


async def authorize(request: Request, user: Estimator = Depends(current_user)) -> Estimator:
    """Signed in, and the role is enough for this request."""
    keys = await _body_keys(request)
    role_needed = needed(request.method, request.url.path, keys)
    if RANK.get(user.role, -1) < RANK[role_needed]:
        raise HTTPException(
            status_code=403,
            detail=(
                f"That takes {LABEL[role_needed]} or above; you are signed in as "
                f"{user.full_name}, {LABEL[user.role]}."
            ),
        )
    return user
