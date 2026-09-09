"""
Concrete orders (sql/086): the pour planned, beside the daily report of it.

    /concrete-orders             list (job, supplier, status, pour dates, search), file one
    /concrete-orders/meta        the statuses
    /concrete-orders/{id}        read, edit, delete

The job and supplier lists are the daily report form's (/daily-reports/meta).
A foreman (app/policy.py) may read here and file an order; the office edits;
a senior deletes.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models.concrete_order import ORDER_STATUSES, ConcreteOrder
from app.models.daily_report import FieldJob
from app.models.estimator import Estimator
from app.schemas.concrete_order import ConcreteOrderCreate, ConcreteOrderRead, ConcreteOrderUpdate

router = APIRouter(prefix="/concrete-orders", tags=["concrete-orders"])


def _or_404(db: Session, order_id: UUID) -> ConcreteOrder:
    row = db.get(ConcreteOrder, order_id)
    if not row:
        raise HTTPException(status_code=404, detail="Concrete order not found")
    return row


def _job_or_400(db: Session, job_id: int) -> FieldJob:
    job = db.get(FieldJob, job_id)
    if job is None:
        raise HTTPException(status_code=400, detail="Unknown job")
    return job


def _read(db: Session, row: ConcreteOrder, people: dict | None = None) -> ConcreteOrderRead:
    if people is None:
        people = {}
        if row.created_by:
            person = db.get(Estimator, row.created_by)
            if person is not None:
                people[person.id] = person.full_name
    return ConcreteOrderRead(
        id=row.id, ordered_on=row.ordered_on, job_id=row.job_id, job_name=row.job.name if row.job else "",
        supplier=row.supplier, pour_date=row.pour_date, pour_time=row.pour_time, yards=row.yards, mix=row.mix,
        order_number=row.order_number, ordered_by=row.ordered_by, notes=row.notes, status=row.status,
        created_by=row.created_by, created_by_name=people.get(row.created_by) if row.created_by else None,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.get("/meta/statuses", response_model=list[str])
def order_statuses() -> list[str]:
    return list(ORDER_STATUSES)


@router.get("", response_model=list[ConcreteOrderRead])
def list_concrete_orders(
    job_id: int | None = Query(None),
    supplier: str | None = Query(None, description="Substring match"),
    status_filter: str | None = Query(None, alias="status"),
    date_from: date | None = Query(None, description="Pour date from"),
    date_to: date | None = Query(None, description="Pour date to"),
    q: str | None = Query(None, description="Search the job, supplier, mix, order number, ordered by, notes"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ConcreteOrderRead]:
    stmt = select(ConcreteOrder).order_by(
        ConcreteOrder.pour_date, ConcreteOrder.pour_time.nulls_last(), ConcreteOrder.created_at
    )
    if job_id is not None:
        stmt = stmt.where(ConcreteOrder.job_id == job_id)
    if supplier:
        stmt = stmt.where(ConcreteOrder.supplier.ilike(f"%{supplier}%"))
    if status_filter:
        stmt = stmt.where(ConcreteOrder.status == status_filter)
    if date_from is not None:
        stmt = stmt.where(ConcreteOrder.pour_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ConcreteOrder.pour_date <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                ConcreteOrder.supplier.ilike(like), ConcreteOrder.mix.ilike(like), ConcreteOrder.order_number.ilike(like),
                ConcreteOrder.ordered_by.ilike(like), ConcreteOrder.notes.ilike(like),
                ConcreteOrder.job_id.in_(select(FieldJob.id).where(FieldJob.name.ilike(like))),
            )
        )
    rows = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    ids = {r.created_by for r in rows if r.created_by}
    people = {e.id: e.full_name for e in db.scalars(select(Estimator).where(Estimator.id.in_(ids))).all()} if ids else {}
    return [_read(db, r, people) for r in rows]


@router.post("", response_model=ConcreteOrderRead, status_code=status.HTTP_201_CREATED)
def create_concrete_order(
    body: ConcreteOrderCreate, db: Session = Depends(get_db), user: Estimator = Depends(current_user)
) -> ConcreteOrderRead:
    _job_or_400(db, body.job_id)
    data = body.model_dump()
    data["status"] = body.status.value
    if data.get("ordered_on") is None:
        data.pop("ordered_on")  # the column's default: today
    if not data.get("ordered_by"):
        data["ordered_by"] = user.full_name
    row = ConcreteOrder(created_by=user.id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.get("/{order_id}", response_model=ConcreteOrderRead)
def get_concrete_order(order_id: UUID, db: Session = Depends(get_db)) -> ConcreteOrderRead:
    return _read(db, _or_404(db, order_id))


@router.patch("/{order_id}", response_model=ConcreteOrderRead)
def update_concrete_order(order_id: UUID, body: ConcreteOrderUpdate, db: Session = Depends(get_db)) -> ConcreteOrderRead:
    row = _or_404(db, order_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value
    for k in ("job_id", "supplier", "pour_date", "yards", "ordered_on", "status"):
        if k in data and data[k] is None:
            data.pop(k)  # blank never empties what the order must have
    if "job_id" in data:
        _job_or_400(db, data["job_id"])
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_concrete_order(order_id: UUID, db: Session = Depends(get_db)) -> None:
    row = _or_404(db, order_id)
    db.delete(row)
    db.commit()
