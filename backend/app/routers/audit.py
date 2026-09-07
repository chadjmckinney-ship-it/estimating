"""The activity feed: who changed what (sql/069). Senior estimators and admins."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    at: datetime
    estimator_id: UUID | None
    username: str | None
    method: str
    path: str
    status: int
    body: Any | None
    duration_ms: int | None
    ip: str | None


@router.get("", response_model=list[AuditEntry])
def list_activity(
    limit: int = Query(200, ge=1, le=1000),
    username: str | None = Query(None, description="exactly this person"),
    path: str | None = Query(None, description="a fragment of the route, e.g. mix-designs or a section id"),
    since: datetime | None = Query(None),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id).limit(limit)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    if path:
        stmt = stmt.where(AuditLog.path.ilike(f"%{path}%"))
    if since is not None:
        stmt = stmt.where(AuditLog.at >= since)
    return list(db.scalars(stmt).all())
