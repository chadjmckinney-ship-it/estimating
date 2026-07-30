from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.mix_design import ConcreteSupplier, MixDesign, MixPrice
from app.schemas.mix_design import (
    ConcreteSupplierCreate,
    ConcreteSupplierRead,
    ConcreteSupplierUpdate,
    MixDesignCreate,
    MixDesignRead,
    MixDesignUpdate,
    MixPriceCreate,
    MixPriceRead,
    MixPriceUpdate,
)

router = APIRouter(tags=["mix-designs"])


def _mix_to_read(row: MixDesign) -> MixDesignRead:
    prices: list[MixPriceRead] = []
    for p in row.prices or []:
        prices.append(
            MixPriceRead(
                id=p.id,
                mix_design_id=p.mix_design_id,
                supplier_id=p.supplier_id,
                supplier_name=p.supplier.name if p.supplier else None,
                unit_cost=p.unit_cost,
                price_as_of=p.price_as_of,
                notes=p.notes,
            )
        )
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
        prices=prices,
    )


def _mix_query(db: Session):
    return select(MixDesign).options(
        selectinload(MixDesign.prices).selectinload(MixPrice.supplier)
    )


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


# ---- Prices ----

@router.get("/mix-prices", response_model=list[MixPriceRead])
def list_mix_prices(
    mix_design_id: int | None = None,
    supplier_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[MixPriceRead]:
    stmt = (
        select(MixPrice)
        .options(selectinload(MixPrice.supplier))
        .order_by(MixPrice.mix_design_id, MixPrice.supplier_id)
    )
    if mix_design_id is not None:
        stmt = stmt.where(MixPrice.mix_design_id == mix_design_id)
    if supplier_id is not None:
        stmt = stmt.where(MixPrice.supplier_id == supplier_id)
    out: list[MixPriceRead] = []
    for p in db.scalars(stmt).all():
        out.append(
            MixPriceRead(
                id=p.id,
                mix_design_id=p.mix_design_id,
                supplier_id=p.supplier_id,
                supplier_name=p.supplier.name if p.supplier else None,
                unit_cost=p.unit_cost,
                price_as_of=p.price_as_of,
                notes=p.notes,
            )
        )
    return out


@router.post("/mix-prices", response_model=MixPriceRead, status_code=status.HTTP_201_CREATED)
def create_mix_price(body: MixPriceCreate, db: Session = Depends(get_db)) -> MixPriceRead:
    if not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")
    supplier = db.get(ConcreteSupplier, body.supplier_id)
    if not supplier:
        raise HTTPException(status_code=400, detail="supplier_id not found")
    row = MixPrice(**body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Price already exists for this mix/supplier/date",
        ) from None
    db.refresh(row)
    return MixPriceRead(
        id=row.id,
        mix_design_id=row.mix_design_id,
        supplier_id=row.supplier_id,
        supplier_name=supplier.name,
        unit_cost=row.unit_cost,
        price_as_of=row.price_as_of,
        notes=row.notes,
    )


@router.patch("/mix-prices/{price_id}", response_model=MixPriceRead)
def update_mix_price(
    price_id: int, body: MixPriceUpdate, db: Session = Depends(get_db)
) -> MixPriceRead:
    row = db.get(MixPrice, price_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mix price not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict updating price") from None
    db.refresh(row)
    supplier = db.get(ConcreteSupplier, row.supplier_id)
    return MixPriceRead(
        id=row.id,
        mix_design_id=row.mix_design_id,
        supplier_id=row.supplier_id,
        supplier_name=supplier.name if supplier else None,
        unit_cost=row.unit_cost,
        price_as_of=row.price_as_of,
        notes=row.notes,
    )
