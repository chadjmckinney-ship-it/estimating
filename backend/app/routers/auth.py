"""Sign in, sign out, who am I, change my password (sql/068); the lockout (sql/083)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_db
from app.models.estimator import Estimator

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=200)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class Me(BaseModel):
    id: UUID
    username: str
    full_name: str
    role: str
    title: str | None = None


def _me(user: Estimator) -> Me:
    return Me(id=user.id, username=user.username, full_name=user.full_name, role=user.role, title=user.title)


@router.post("/login", response_model=Me)
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)) -> Me:
    name = body.username.strip().lower()
    ip = request.client.host if request.client else None
    # Locked names and addresses are refused first (sql/083): no scrypt spent,
    # no extra failure counted, and the right password does not get in either.
    locked = auth.lock_remaining(db, name, ip)
    if locked:
        what, seconds = locked
        minutes = -(-seconds // 60)
        log.warning("locked sign-in for %r from %s (%s, %ss left)", body.username, ip or "?", what, seconds)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many sign-in attempts {'for that username' if what == 'username' else 'from this address'}. "
                f"Try again in {minutes} minute{'' if minutes == 1 else 's'}."
            ),
            headers={"Retry-After": str(seconds)},
        )
    user = db.scalars(select(Estimator).where(func.lower(Estimator.username) == name)).first()
    # One message for an unknown name, a wrong password, no password yet and a
    # deactivated person: the login box is not the place to learn which.
    if user is None or not user.is_active or not auth.verify_password(body.password, user.password_hash):
        log.warning("failed sign-in for %r from %s", body.username, ip or "?")
        auth.note_failure(db, name, ip)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    auth.clear_failures(db, name)
    token = auth.start_session(db, user, request)
    db.commit()
    auth.set_cookie(response, request, token)
    return _me(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    token = request.cookies.get(auth.COOKIE)
    if token:
        auth.end_session(db, token)
        db.commit()
    auth.clear_cookie(response)


@router.get("/me", response_model=Me)
def me(user: Estimator = Depends(auth.current_user)) -> Me:
    return _me(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    request: Request,
    user: Estimator = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> None:
    """My own password. Every other session of mine ends; this one stays."""
    if not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    user.password_hash = auth.hash_password(body.new_password)
    auth.end_other_sessions(db, user, request.cookies.get(auth.COOKIE))
    db.commit()
