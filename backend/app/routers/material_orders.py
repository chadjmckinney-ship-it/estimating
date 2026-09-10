"""
Material orders (sql/087): rebar, post-tension and the rest, beside the concrete orders.

    /material-orders             list (kind, job, supplier, status, needed-by dates, search), file one
    /material-orders/meta        the kinds, the units, the statuses, the suppliers used before
    /material-orders/summary     what each job has ordered, by kind and unit
    /material-orders/{id}        read, edit, delete

The job list is the daily report form's (/daily-reports/meta). A foreman
(app/policy.py) may read here and file an order; the office edits; a
senior deletes.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models.daily_report import FieldJob
from app.models.estimator import Estimator
from app.models.material_order import KIND_LABELS, KINDS, MATERIAL_STATUSES, UNITS, MaterialOrder
from app.schemas.material_order import (
    MaterialOrderCreate,
    MaterialOrderMeta,
    MaterialOrderRead,
    MaterialOrderUpdate,
    MaterialSummaryRow,
)

router = APIRouter(prefix="/material-orders", tags=["material-orders"])


def _or_404(db: Session, order_id: UUID) -> MaterialOrder:
    row = db.get(MaterialOrder, order_id)
    if not row:
        raise HTTPException(status_code=404, detail="Material order not found")
    return row


def _job_or_400(db: Session, job_id: int) -> FieldJob:
    job = db.get(FieldJob, job_id)
    if job is None:
        raise HTTPException(status_code=400, detail="Unknown job")
    return job


def _read(db: Session, row: MaterialOrder, people: dict | None = None) -> MaterialOrderRead:
    if people is None:
        people = {}
        if row.created_by:
            person = db.get(Estimator, row.created_by)
            if person is not None:
                people[person.id] = person.full_name
    return MaterialOrderRead(
        id=row.id, kind=row.kind, ordered_on=row.ordered_on, job_id=row.job_id,
        job_name=row.job.name if row.job else "", supplier=row.supplier, description=row.description,
        quantity=row.quantity, unit=row.unit, needed_by=row.needed_by, delivered_on=row.delivered_on,
        order_number=row.order_number, ordered_by=row.ordered_by, notes=row.notes, status=row.status,
        created_by=row.created_by, created_by_name=people.get(row.created_by) if row.created_by else None,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.get("/meta", response_model=MaterialOrderMeta)
def material_order_meta(db: Session = Depends(get_db)) -> MaterialOrderMeta:
    db.flush()
    seen = db.execute(
        select(MaterialOrder.supplier, func.max(MaterialOrder.created_at))
        .group_by(MaterialOrder.supplier)
        .order_by(func.max(MaterialOrder.created_at).desc())
    ).all()
    return MaterialOrderMeta(
        kinds=[{"key": k, "en": KIND_LABELS[k][0], "es": KIND_LABELS[k][1]} for k in KINDS],
        units=list(UNITS),
        statuses=list(MATERIAL_STATUSES),
        suppliers=[s for s, _ in seen],
    )


@router.get("/summary", response_model=list[MaterialSummaryRow])
def material_order_summary(
    job_id: int | None = Query(None), kind: str | None = Query(None), db: Session = Depends(get_db)
) -> list[MaterialSummaryRow]:
    """What each job has ordered, by kind and unit; canceled orders left out."""
    db.flush()
    stmt = (
        select(
            MaterialOrder.job_id, FieldJob.name, MaterialOrder.kind, MaterialOrder.unit,
            func.count(MaterialOrder.id), func.coalesce(func.sum(MaterialOrder.quantity), 0),
        )
        .join(FieldJob, FieldJob.id == MaterialOrder.job_id)
        .where(MaterialOrder.status != "canceled")
        .group_by(MaterialOrder.job_id, FieldJob.name, MaterialOrder.kind, MaterialOrder.unit)
        .order_by(FieldJob.name, MaterialOrder.kind, MaterialOrder.unit)
    )
    if job_id is not None:
        stmt = stmt.where(MaterialOrder.job_id == job_id)
    if kind:
        stmt = stmt.where(MaterialOrder.kind == kind)
    return [
        MaterialSummaryRow(job_id=j, job_name=name, kind=k, unit=u, orders=n, quantity=q)
        for j, name, k, u, n, q in db.execute(stmt).all()
    ]


@router.get("", response_model=list[MaterialOrderRead])
def list_material_orders(
    kind: str | None = Query(None),
    job_id: int | None = Query(None),
    supplier: str | None = Query(None, description="Substring match"),
    status_filter: str | None = Query(None, alias="status"),
    date_from: date | None = Query(None, description="Needed by, from"),
    date_to: date | None = Query(None, description="Needed by, to"),
    q: str | None = Query(None, description="Search the job, supplier, description, order number, ordered by, notes"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MaterialOrderRead]:
    stmt = select(MaterialOrder).order_by(MaterialOrder.needed_by.nulls_last(), MaterialOrder.created_at)
    if kind:
        stmt = stmt.where(MaterialOrder.kind == kind)
    if job_id is not None:
        stmt = stmt.where(MaterialOrder.job_id == job_id)
    if supplier:
        stmt = stmt.where(MaterialOrder.supplier.ilike(f"%{supplier}%"))
    if status_filter:
        stmt = stmt.where(MaterialOrder.status == status_filter)
    if date_from is not None:
        stmt = stmt.where(MaterialOrder.needed_by >= date_from)
    if date_to is not None:
        stmt = stmt.where(MaterialOrder.needed_by <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                MaterialOrder.supplier.ilike(like), MaterialOrder.description.ilike(like),
                MaterialOrder.order_number.ilike(like), MaterialOrder.ordered_by.ilike(like),
                MaterialOrder.notes.ilike(like),
                MaterialOrder.job_id.in_(select(FieldJob.id).where(FieldJob.name.ilike(like))),
            )
        )
    rows = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    ids = {r.created_by for r in rows if r.created_by}
    people = {e.id: e.full_name for e in db.scalars(select(Estimator).where(Estimator.id.in_(ids))).all()} if ids else {}
    return [_read(db, r, people) for r in rows]


@router.post("", response_model=MaterialOrderRead, status_code=status.HTTP_201_CREATED)
def create_material_order(
    body: MaterialOrderCreate, db: Session = Depends(get_db), user: Estimator = Depends(current_user)
) -> MaterialOrderRead:
    _job_or_400(db, body.job_id)
    data = body.model_dump()
    data["kind"] = body.kind.value
    data["status"] = body.status.value
    if data.get("ordered_on") is None:
        data.pop("ordered_on")  # the column's default: today
    if not data.get("ordered_by"):
        data["ordered_by"] = user.full_name
    if data["status"] == "delivered" and data.get("delivered_on") is None:
        data["delivered_on"] = date.today()
    row = MaterialOrder(created_by=user.id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.get("/{order_id}", response_model=MaterialOrderRead)
def get_material_order(order_id: UUID, db: Session = Depends(get_db)) -> MaterialOrderRead:
    return _read(db, _or_404(db, order_id))


@router.patch("/{order_id}", response_model=MaterialOrderRead)
def update_material_order(order_id: UUID, body: MaterialOrderUpdate, db: Session = Depends(get_db)) -> MaterialOrderRead:
    row = _or_404(db, order_id)
    data = body.model_dump(exclude_unset=True)
    for k in ("kind", "status"):
        if k in data and data[k] is not None:
            data[k] = data[k].value
    for k in ("kind", "job_id", "supplier", "description", "ordered_on", "status"):
        if k in data and data[k] is None:
            data.pop(k)  # blank never empties what the order must have
    if "job_id" in data:
        _job_or_400(db, data["job_id"])
    for k, v in data.items():
        setattr(row, k, v)
    if row.status == "delivered" and row.delivered_on is None:
        row.delivered_on = date.today()
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material_order(order_id: UUID, db: Session = Depends(get_db)) -> None:
    row = _or_404(db, order_id)
    db.delete(row)
    db.commit()
