from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimator import Estimator
from app.schemas.estimator import EstimatorCreate, EstimatorRead, EstimatorUpdate

router = APIRouter(prefix="/estimators", tags=["estimators"])


@router.get("", response_model=list[EstimatorRead])
def list_estimators(
    active_only: bool = Query(False, description="If true, only is_active=true"),
    role: str | None = Query(None, description="Filter by role: admin|estimator|viewer"),
    db: Session = Depends(get_db),
) -> list[Estimator]:
    stmt = select(Estimator).order_by(Estimator.full_name)
    if active_only:
        stmt = stmt.where(Estimator.is_active.is_(True))
    if role:
        stmt = stmt.where(Estimator.role == role)
    return list(db.scalars(stmt).all())


@router.get("/{estimator_id}", response_model=EstimatorRead)
def get_estimator(estimator_id: UUID, db: Session = Depends(get_db)) -> Estimator:
    row = db.get(Estimator, estimator_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimator not found")
    return row


@router.post("", response_model=EstimatorRead, status_code=status.HTTP_201_CREATED)
def create_estimator(body: EstimatorCreate, db: Session = Depends(get_db)) -> Estimator:
    row = Estimator(
        username=body.username.strip(),
        full_name=body.full_name.strip(),
        email=str(body.email) if body.email else None,
        phone=body.phone,
        title=body.title,
        role=body.role.value,
        notes=body.notes,
        is_active=body.is_active,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' already exists",
        ) from None
    db.refresh(row)
    return row


@router.patch("/{estimator_id}", response_model=EstimatorRead)
def update_estimator(
    estimator_id: UUID,
    body: EstimatorUpdate,
    db: Session = Depends(get_db),
) -> Estimator:
    row = db.get(Estimator, estimator_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimator not found")

    data = body.model_dump(exclude_unset=True)
    if "role" in data and data["role"] is not None:
        data["role"] = data["role"].value if hasattr(data["role"], "value") else data["role"]
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    if "username" in data and data["username"] is not None:
        data["username"] = data["username"].strip()
    if "full_name" in data and data["full_name"] is not None:
        data["full_name"] = data["full_name"].strip()

    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        ) from None
    db.refresh(row)
    return row


@router.delete("/{estimator_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_estimator(estimator_id: UUID, db: Session = Depends(get_db)) -> None:
    """Soft-delete: set is_active=false (keeps FK history)."""
    row = db.get(Estimator, estimator_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimator not found")
    row.is_active = False
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
