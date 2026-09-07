"""
Who changed what (sql/069).

Two layers, both keyed to the signed-in person that app/auth.py notes on the
request's database session (`session.info["actor"]`) for the life of the
request:

  * `AuditMiddleware` writes one `audit_log` row for every write request
    that reached the API — method, route, the JSON sent (password fields
    blanked; a sign-in body is never kept, only the username tried), the
    status it got, how long it took. A route that writes through raw SQL is
    covered exactly like one that writes through the ORM.

  * `_stamp`, a before-flush hook on every ORM session, sets `updated_by`
    on a new row and on an edit that changed an INPUT — anything that is not
    a calc_* column or a housekeeping timestamp. A recalc that rewrites
    every pour's calc_* columns is the setting's author's doing, not the
    pour's, and leaves the pour's stamp alone. The three raw-SQL writers
    (job rules, section rates, company settings) stamp by hand with `actor()`.

The log must never break the request it records: a failure to write it is
logged and swallowed.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.audit_log import AuditLog

log = logging.getLogger(__name__)

# Attribute changes that are not a person changing an input.
_HOUSEKEEPING = frozenset({
    "updated_at", "updated_by", "refreshed_at", "pulled_at", "last_seen_at", "calc_at",
})
_WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SECRET = "password"


def set_actor(session: Session, estimator_id: uuid.UUID | None) -> None:
    """Note who is driving this session. A sync dependency runs in a worker
    thread with a copy of the request context, so a context variable would
    never reach the route; the session is the one object they all share."""
    session.info["actor"] = estimator_id


def actor(session: Session) -> uuid.UUID | None:
    """The signed-in person behind this session, or None (a script, a test fixture)."""
    return session.info.get("actor")


# ------------------------------------------------------------ updated_by --


def _input_changed(obj: Any) -> bool:
    for attr in inspect(obj).attrs:
        if attr.key.startswith("calc_") or attr.key in _HOUSEKEEPING:
            continue
        if attr.history.has_changes():
            return True
    return False


def _stamp(session: Session, flush_context, instances) -> None:
    who = actor(session)
    if who is None:
        return
    for obj in session.new:
        if hasattr(obj, "updated_by") and getattr(obj, "updated_by", None) is None:
            obj.updated_by = who
    for obj in session.dirty:
        if hasattr(obj, "updated_by") and session.is_modified(obj) and _input_changed(obj):
            obj.updated_by = who


event.listen(Session, "before_flush", _stamp)


# -------------------------------------------------------------- the log --


def redact(data: Any) -> Any:
    """Blank every value whose key mentions a password, however deep."""
    if isinstance(data, dict):
        return {
            k: ("•••" if _SECRET in str(k).lower() else redact(v)) for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact(v) for v in data]
    return data


def record(scope: dict, status: int, started: float, body: bytes) -> None:
    """One audit_log row for the request in `scope`. Raises nothing the caller must handle."""
    state = scope.get("state") or {}
    user = state.get("user")
    path = scope["path"]
    data: Any = None
    if body:
        try:
            data = json.loads(body)
        except ValueError:
            data = {"_raw": body[:2000].decode("utf-8", errors="replace")}
    username = getattr(user, "username", None)
    if path == "/api/auth/login":
        # The attempt is the record — who tried, and whether it worked. The
        # body itself is never kept, redacted or not.
        if isinstance(data, dict) and username is None:
            username = str(data.get("username") or "")[:64] or None
        data = None
    else:
        data = redact(data)
    client = scope.get("client")
    row = AuditLog(
        # Stamped here, not by the column default: now() is the transaction's
        # start, so every row a test writes would share one instant and the
        # feed's order would be a coin toss.
        at=datetime.now(timezone.utc),
        estimator_id=getattr(user, "id", None),
        username=username,
        method=scope["method"],
        path=path,
        status=int(status),
        body=data,
        duration_ms=int((perf_counter() - started) * 1000),
        ip=client[0] if client else None,
    )
    db = state.get("audit_db")
    if db is not None:
        # The test suite hands its own rolled-back session in (tests/conftest.py).
        db.add(row)
        db.flush()
        return
    session = SessionLocal()
    try:
        session.add(row)
        session.commit()
    finally:
        session.close()


class AuditMiddleware:
    """Pure ASGI: captures the request body on the way in and the status on the way out."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] not in _WRITES
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        chunks: list[bytes] = []
        status = {"code": 500}

        async def receive_and_keep():
            message = await receive()
            if message["type"] == "http.request":
                chunks.append(message.get("body", b""))
            return message

        async def send_and_note(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive_and_keep, send_and_note)
        finally:
            try:
                record(scope, status["code"], started, b"".join(chunks))
            except Exception:  # noqa: BLE001 — the log never breaks the request
                log.exception("audit_log write failed for %s %s", scope["method"], scope["path"])
