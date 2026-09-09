"""
The bid list (sql/082): every invite as it came in, apart from projects.

    /bid-requests                 list (status, estimator, gc, q, due window), make
    /bid-requests/meta/statuses   the five statuses
    /bid-requests/{id}            read, edit, delete
    /bid-requests/{id}/estimate   "Estimate this": the bid becomes a project
    /bid-requests/import          a Notion export, upserted by page id
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models.bid_request import BID_STATUSES, BidRequest, BidRequestEstimator
from app.models.estimator import Estimator
from app.schemas.bid_request import (
    BidRequestCreate,
    BidRequestRead,
    BidRequestUpdate,
    EstimateThisResult,
    ImportResult,
)
from app.services.bid_requests import EstimateThisError, estimate_this, import_rows, set_estimators, to_read

router = APIRouter(prefix="/bid-requests", tags=["bid-requests"])


def _read(db: Session, row: BidRequest) -> BidRequestRead:
    return BidRequestRead(**to_read(db, row))


def _or_404(db: Session, bid_id: UUID) -> BidRequest:
    row = db.get(BidRequest, bid_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bid request not found")
    return row


def _conflict(exc: IntegrityError) -> HTTPException:
    what = "message id" if "message_id" in str(exc.orig) else "Notion page id" if "notion_page_id" in str(exc.orig) else "row"
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A bid with that {what} is already on the list")


@router.get("/meta/statuses", response_model=list[str])
def bid_statuses() -> list[str]:
    return list(BID_STATUSES)


@router.get("", response_model=list[BidRequestRead])
def list_bid_requests(
    status_filter: str | None = Query(None, alias="status"),
    estimator_id: UUID | None = Query(None),
    gc: str | None = Query(None, description="Substring match on GC"),
    q: str | None = Query(None, description="Search name / location / GC / notes"),
    due_from: date | None = Query(None),
    due_to: date | None = Query(None),
    db: Session = Depends(get_db),
) -> list[BidRequestRead]:
    stmt = select(BidRequest).order_by(BidRequest.bid_due.nulls_last(), BidRequest.bid_due_time.nulls_last(), BidRequest.name)
    if status_filter:
        stmt = stmt.where(BidRequest.status == status_filter)
    if estimator_id:
        stmt = stmt.where(
            BidRequest.id.in_(
                select(BidRequestEstimator.bid_request_id).where(BidRequestEstimator.estimator_id == estimator_id)
            )
        )
    if gc:
        stmt = stmt.where(BidRequest.gc.ilike(f"%{gc}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                BidRequest.name.ilike(like),
                BidRequest.location.ilike(like),
                BidRequest.gc.ilike(like),
                BidRequest.notes.ilike(like),
            )
        )
    if due_from:
        stmt = stmt.where(BidRequest.bid_due >= due_from)
    if due_to:
        stmt = stmt.where(BidRequest.bid_due <= due_to)
    return [_read(db, r) for r in db.scalars(stmt).unique().all()]


@router.post("", response_model=BidRequestRead, status_code=status.HTTP_201_CREATED)
def create_bid_request(body: BidRequestCreate, db: Session = Depends(get_db)) -> BidRequestRead:
    data = body.model_dump(exclude={"estimator_ids"})
    data["status"] = body.status.value
    data["name"] = data["name"].strip()
    row = BidRequest(**data)
    db.add(row)
    try:
        db.flush()
        missing = set_estimators(db, row, body.estimator_ids)
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown estimator_ids: {missing}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict(exc) from exc
    db.refresh(row)
    return _read(db, row)


@router.post("/import", response_model=ImportResult)
def import_bid_requests(rows: list[dict] = Body(...), db: Session = Depends(get_db)) -> ImportResult:
    """A Notion export — the MCP's rows or SQL mode — loaded onto the list."""
    if len(rows) > 2000:
        raise HTTPException(status_code=400, detail="Send the export in pieces of 2,000 rows or fewer")
    result = import_rows(db, rows)
    db.commit()
    return ImportResult(**result)


@router.get("/{bid_id}", response_model=BidRequestRead)
def get_bid_request(bid_id: UUID, db: Session = Depends(get_db)) -> BidRequestRead:
    return _read(db, _or_404(db, bid_id))


@router.patch("/{bid_id}", response_model=BidRequestRead)
def update_bid_request(bid_id: UUID, body: BidRequestUpdate, db: Session = Depends(get_db)) -> BidRequestRead:
    row = _or_404(db, bid_id)
    data = body.model_dump(exclude_unset=True)
    ids = data.pop("estimator_ids", None)
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value
    for k, v in data.items():
        if k == "name" and v is None:
            continue
        setattr(row, k, v)
    if ids is not None:
        missing = set_estimators(db, row, ids)
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown estimator_ids: {missing}")
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict(exc) from exc
    db.refresh(row)
    return _read(db, row)


@router.delete("/{bid_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bid_request(bid_id: UUID, db: Session = Depends(get_db)) -> None:
    row = _or_404(db, bid_id)
    db.delete(row)
    db.commit()


@router.post("/{bid_id}/estimate", response_model=EstimateThisResult)
def estimate_bid_request(
    bid_id: UUID, db: Session = Depends(get_db), user: Estimator = Depends(current_user)
) -> EstimateThisResult:
    """The bid becomes a project, linked both ways; a second press is refused."""
    row = _or_404(db, bid_id)
    try:
        project = estimate_this(db, row, user.id)
    except EstimateThisError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A project with this invite's message id already exists; open Projects and look for it",
        ) from exc
    db.commit()
    db.refresh(row)
    return EstimateThisResult(bid=_read(db, row), project_id=project.id)
