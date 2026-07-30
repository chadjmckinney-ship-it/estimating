from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.equipment import Equipment
from app.schemas.equipment import EquipmentCreate, EquipmentRead, EquipmentUpdate

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("", response_model=list[EquipmentRead])
def list_equipment(
    active_only: bool = Query(True),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[Equipment]:
    stmt = select(Equipment).order_by(Equipment.sort_order, Equipment.name)
    if active_only:
        stmt = stmt.where(Equipment.is_active.is_(True))
    if category:
        stmt = stmt.where(Equipment.category == category)
    return list(db.scalars(stmt).all())


@router.get("/meta/categories", response_model=list[str])
def list_categories() -> list[str]:
    return ["earthwork", "lifting", "power", "hauling", "pumping", "other"]


@router.get("/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: int, db: Session = Depends(get_db)) -> Equipment:
    row = db.get(Equipment, equipment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return row


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(body: EquipmentCreate, db: Session = Depends(get_db)) -> Equipment:
    data = body.model_dump()
    data["name"] = body.name.strip()
    if data.get("code"):
        data["code"] = data["code"].strip().upper()
    data["category"] = body.category.value
    data["unit"] = body.unit.strip().upper()
    row = Equipment(**data)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Equipment with this name/unit or code already exists",
        ) from None
    db.refresh(row)
    return row


@router.patch("/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: int, body: EquipmentUpdate, db: Session = Depends(get_db)
) -> Equipment:
    row = db.get(Equipment, equipment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Equipment not found")
    data = body.model_dump(exclude_unset=True)
    if "category" in data and data["category"] is not None:
        data["category"] = data["category"].value
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "code" in data and data["code"] is not None:
        data["code"] = data["code"].strip().upper()
    if "unit" in data and data["unit"] is not None:
        data["unit"] = data["unit"].strip().upper()
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict updating equipment") from None
    db.refresh(row)
    return row


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_equipment(equipment_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Equipment, equipment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Equipment not found")
    row.is_active = False
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
