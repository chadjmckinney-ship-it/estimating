from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.mix_design import ConcreteSupplier, MixDesign
from app.schemas.mix_design import (
    ConcreteSupplierCreate,
    ConcreteSupplierRead,
    ConcreteSupplierUpdate,
    MixDesignCreate,
    MixDesignRead,
    MixDesignUpdate,
)

router = APIRouter(tags=["mix-designs"])


def _mix_to_read(row: MixDesign) -> MixDesignRead:
    return MixDesignRead(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        strength_psi=row.strength_psi,
        has_ash=row.has_ash,
        has_air=row.has_air,
        sack_count=row.sack_count,
        typical_use=row.typical_use,
        unit=row.unit,
        unit_cost=row.unit_cost,
        sort_order=row.sort_order,
        notes=row.notes,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _mix_query(db: Session):
    return select(MixDesign)


# ---- Mix designs ----

@router.get("/mix-designs", response_model=list[MixDesignRead])
def list_mix_designs(
    active_only: bool = Query(True),
    strength_psi: int | None = Query(None),
    db: Session = Depends(get_db),
) -> list[MixDesignRead]:
    stmt = _mix_query(db).order_by(MixDesign.sort_order, MixDesign.code)
    if active_only:
        stmt = stmt.where(MixDesign.is_active.is_(True))
    if strength_psi is not None:
        stmt = stmt.where(MixDesign.strength_psi == strength_psi)
    return [_mix_to_read(r) for r in db.scalars(stmt).unique().all()]


@router.get("/mix-designs/{mix_id}", response_model=MixDesignRead)
def get_mix_design(mix_id: int, db: Session = Depends(get_db)) -> MixDesignRead:
    row = db.scalars(_mix_query(db).where(MixDesign.id == mix_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Mix design not found")
    return _mix_to_read(row)


@router.post("/mix-designs", response_model=MixDesignRead, status_code=status.HTTP_201_CREATED)
def create_mix_design(body: MixDesignCreate, db: Session = Depends(get_db)) -> MixDesignRead:
    data = body.model_dump()
    data["code"] = body.code.strip()
    data["name"] = body.name.strip()
    row = MixDesign(**data)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Code '{body.code}' already exists") from None
    db.refresh(row)
    row = db.scalars(_mix_query(db).where(MixDesign.id == row.id)).one()
    return _mix_to_read(row)


@router.patch("/mix-designs/{mix_id}", response_model=MixDesignRead)
def update_mix_design(
    mix_id: int, body: MixDesignUpdate, db: Session = Depends(get_db)
) -> MixDesignRead:
    row = db.get(MixDesign, mix_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mix design not found")
    data = body.model_dump(exclude_unset=True)
    if "code" in data and data["code"] is not None:
        data["code"] = data["code"].strip()
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Code already exists") from None
    row = db.scalars(_mix_query(db).where(MixDesign.id == mix_id)).one()
    return _mix_to_read(row)


@router.delete("/mix-designs/{mix_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_mix_design(mix_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(MixDesign, mix_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mix design not found")
    row.is_active = False
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


# ---- Suppliers ----

@router.get("/concrete-suppliers", response_model=list[ConcreteSupplierRead])
def list_suppliers(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
) -> list[ConcreteSupplier]:
    stmt = select(ConcreteSupplier).order_by(ConcreteSupplier.name)
    if active_only:
        stmt = stmt.where(ConcreteSupplier.is_active.is_(True))
    return list(db.scalars(stmt).all())


@router.post(
    "/concrete-suppliers",
    response_model=ConcreteSupplierRead,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    body: ConcreteSupplierCreate, db: Session = Depends(get_db)
) -> ConcreteSupplier:
    row = ConcreteSupplier(**body.model_dump())
    row.name = body.name.strip()
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier name already exists") from None
    db.refresh(row)
    return row


@router.patch("/concrete-suppliers/{supplier_id}", response_model=ConcreteSupplierRead)
def update_supplier(
    supplier_id: int, body: ConcreteSupplierUpdate, db: Session = Depends(get_db)
) -> ConcreteSupplier:
    row = db.get(ConcreteSupplier, supplier_id)
    if not row:
        raise HTTPException(status_code=404, detail="Supplier not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier name already exists") from None
    db.refresh(row)
    return row
