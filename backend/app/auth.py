"""
Passwords, sessions, and who is signed in (sql/068).

Passwords are scrypt from the standard library — no new dependency — with a
per-user salt, stored as `scrypt$N$r$p$salt$key` so the work factor can rise
later without a migration. A session is a random token in an HttpOnly,
SameSite=Lax cookie; the table holds the token's SHA-256, so a copy of the
table is not a set of keys. A session ends after 12 idle hours or 30 days,
whichever comes first, on sign-out, or when the person's password is reset.

`current_user` is the dependency every protected route goes through (see
app/policy.py for what each role may do); the login route is the one API
route that does not.

The login box is not a free guess (sql/083, the day the app went public
through Tailscale Funnel): every wrong sign-in is a login_failures row, and
five for one name or twenty from one address inside fifteen minutes lock
that name or address for fifteen minutes from the last of them. A locked
try is a 429 with a Retry-After, refused before the password is looked at.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.models.estimator import Estimator
from app.models.login_failure import LoginFailure
from app.models.session import LoginSession

log = logging.getLogger(__name__)

COOKIE = "estimating_session"
IDLE = timedelta(hours=12)
ABSOLUTE = timedelta(days=30)
TOUCH_EVERY = timedelta(minutes=5)

# The lockout (sql/083). A name is locked by its fifth failure in the window,
# an address by its twentieth, each until the window has passed since that
# failure. Five is a person mistyping; twenty from one address is a script.
LOCK_WINDOW = timedelta(minutes=15)
LOCK_AFTER_PER_NAME = 5
LOCK_AFTER_PER_IP = 20
FAILURES_KEPT = timedelta(days=1)

# scrypt work factors. 2**15 is ~150 ms on this box, which is the point: a
# stolen table costs an attacker that per guess. The test suite lowers N
# through the environment (tests/conftest.py) so 800 logins do not cost a
# minute; the stored string carries its own N, so both verify.
_N = int(os.environ.get("ESTIMATING_SCRYPT_N", str(2**15)))
_R, _P = 8, 1


def _maxmem(n: int, r: int) -> int:
    # scrypt needs 128*N*r bytes of working memory, and hashlib's default
    # ceiling is 32 MiB — which 2**15 * 8 fills exactly, so the first real
    # sign-in raised "memory limit exceeded" (Chad, 2026-09-07; the suite
    # runs at a lighter N and never saw it). Ask for what the parameters
    # need, with room to spare.
    return 128 * n * r + 4 * 2**20


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32, maxmem=_maxmem(_N, _R)
    )
    return "$".join(
        ("scrypt", str(_N), str(_R), str(_P), base64.b64encode(salt).decode(), base64.b64encode(key).decode())
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, key = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(key)
        got = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(want), maxmem=_maxmem(int(n), int(r)),
        )
        return hmac.compare_digest(got, want)
    except Exception:  # noqa: BLE001 — a malformed hash is a failed login, not a 500
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_session(db: Session, user: Estimator, request: Request) -> str:
    """Open a session for `user`; returns the cookie value. Flushes, does not commit."""
    token = secrets.token_urlsafe(32)
    now = _now()
    db.add(LoginSession(
        estimator_id=user.id,
        token_hash=_token_hash(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + ABSOLUTE,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        ip=request.client.host if request.client else None,
    ))
    # Housekeeping while we are here: what has expired goes.
    db.execute(delete(LoginSession).where(
        (LoginSession.expires_at < now) | (LoginSession.last_seen_at < now - IDLE)
    ))
    db.flush()
    return token


def end_session(db: Session, token: str) -> None:
    db.execute(delete(LoginSession).where(LoginSession.token_hash == _token_hash(token)))


def end_other_sessions(db: Session, user: Estimator, keep_token: str | None) -> None:
    """After a password change: every other session of this person ends."""
    stmt = delete(LoginSession).where(LoginSession.estimator_id == user.id)
    if keep_token:
        stmt = stmt.where(LoginSession.token_hash != _token_hash(keep_token))
    db.execute(stmt)


def session_user(db: Session, token: str) -> Estimator | None:
    """The active person behind a cookie value, or None. Touches last_seen_at."""
    row = db.scalars(select(LoginSession).where(LoginSession.token_hash == _token_hash(token))).first()
    if row is None:
        return None
    now = _now()
    if row.expires_at < now or row.last_seen_at < now - IDLE:
        db.delete(row)
        db.commit()
        return None
    user = db.get(Estimator, row.estimator_id)
    if user is None or not user.is_active:
        return None
    if now - row.last_seen_at > TOUCH_EVERY:
        row.last_seen_at = now
        db.commit()
    return user


def lock_remaining(db: Session, username: str, ip: str | None) -> tuple[str, int] | None:
    """
    ('username' | 'address', seconds left) while `username` or `ip` is locked,
    else None. `username` is the name as typed, lowercased and trimmed; it need
    not exist, so a guessed name locks the same as a real one.
    """
    now = _now()
    for what, column, value, limit in (
        ("username", LoginFailure.username, username, LOCK_AFTER_PER_NAME),
        ("address", LoginFailure.ip, ip, LOCK_AFTER_PER_IP),
    ):
        if not value:
            continue
        # The newest `limit` failures inside the window. When there are that
        # many, the lock ends when the oldest of them leaves the window.
        stamps = db.scalars(
            select(LoginFailure.failed_at)
            .where(column == value, LoginFailure.failed_at > now - LOCK_WINDOW)
            .order_by(LoginFailure.failed_at.desc())
            .limit(limit)
        ).all()
        if len(stamps) >= limit:
            until = stamps[-1] + LOCK_WINDOW
            return what, max(1, int((until - now).total_seconds()))
    return None


def note_failure(db: Session, username: str, ip: str | None) -> None:
    """A wrong sign-in: one row, and the rows older than a day go. Commits."""
    now = _now()
    db.add(LoginFailure(username=username, ip=ip, failed_at=now))
    db.execute(delete(LoginFailure).where(LoginFailure.failed_at < now - FAILURES_KEPT))
    db.commit()


def clear_failures(db: Session, username: str) -> None:
    """A right sign-in: the name's count starts over. Runs at once; the caller commits."""
    db.execute(delete(LoginFailure).where(LoginFailure.username == username))


def set_cookie(response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", path="/",
        secure=request.url.scheme == "https", max_age=int(ABSOLUTE.total_seconds()),
    )


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> Estimator:
    token = request.cookies.get(COOKIE)
    user = session_user(db, token) if token else None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Sign in to use the estimating app",
            headers={"WWW-Authenticate": "Cookie"},
        )
    request.state.user = user
    audit.set_actor(db, user.id)  # who the flush hook and the raw-SQL writers stamp (sql/069)
    return user
