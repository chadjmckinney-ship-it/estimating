"""
The unit-price catalog behind forming, poly, rebar, sand and mesh costing.

Editing a price here does NOT reprice stored estimates: costing reads these
values at recalc time, so a change lands on the next recalc. Use
POST /api/system-settings/recalc-all to push prices through the open estimates
— it deliberately leaves final and archived ones at their bid numbers.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.material import Material
from app.schemas.material import MaterialCreate, MaterialRead, MaterialUpdate

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=list[MaterialRead])
def list_materials(
    active_only: bool = Query(True),
    category: str | None = Query(None),
    q: str | None = Query(None, description="Search name"),
    db: Session = Depends(get_db),
) -> list[Material]:
    stmt = select(Material).order_by(Material.sort_order, Material.name)
    if active_only:
        stmt = stmt.where(Material.is_active.is_(True))
    if category:
        stmt = stmt.where(Material.category == category)
    if q:
        stmt = stmt.where(Material.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt).all())


@router.get("/meta/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db)) -> list[str]:
    rows = db.scalars(
        select(Material.category).where(Material.is_active.is_(True)).distinct()
    ).all()
    return sorted(rows)


@router.get("/{material_id}", response_model=MaterialRead)
def get_material(material_id: int, db: Session = Depends(get_db)) -> Material:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="Material not found")
    return row


@router.post("", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
def create_material(body: MaterialCreate, db: Session = Depends(get_db)) -> Material:
    data = body.model_dump()
    data["name"] = data["name"].strip()
    data["category"] = data["category"].strip()
    data["unit"] = data["unit"].strip().upper()
    if data.get("code"):
        data["code"] = data["code"].strip().upper()
    row = Material(**data)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A material with this name or code already exists"
        ) from None
    db.refresh(row)
    return row


@router.patch("/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: int, body: MaterialUpdate, db: Session = Depends(get_db)
) -> Material:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="Material not found")
    data = body.model_dump(exclude_unset=True)
    for key in ("name", "category"):
        if data.get(key) is not None:
            data[key] = data[key].strip()
    for key in ("unit", "code"):
        if data.get(key) is not None:
            data[key] = data[key].strip().upper()
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict updating material") from None
    db.refresh(row)
    return row


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_material(material_id: int, db: Session = Depends(get_db)) -> None:
    """
    Soft delete. Costing matches materials by name, and forming lines keep a
    material_id, so rows are deactivated rather than removed.
    """
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="Material not found")
    row.is_active = False
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
