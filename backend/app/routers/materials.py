from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.material import Material
from app.schemas.material import MaterialRead, MaterialUpdate

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


@router.patch("/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: int, body: MaterialUpdate, db: Session = Depends(get_db)
) -> Material:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="Material not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
