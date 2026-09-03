"""
The estimate price sheet (sql/048).

    GET   /estimates/{id}/prices              the sheet + drift against the master list
    POST  /estimates/{id}/prices/pull         pull the master list; ?dry_run=true previews
    PATCH /estimates/{id}/prices/{price_id}   edit one price for this job, or reset it

Every write here re-runs the whole estimate. A price on the sheet reaches every
section, so there is no narrower thing to recalculate — and the roll-up rides
along with `refresh_pour_costs` (costing._roll_up_parent).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.estimate_price import EstimatePrice
from app.schemas.estimate_price import (
    EstimatePriceRead,
    EstimatePriceSheetRead,
    EstimatePriceUpdate,
    PullResultRead,
)
from app.services import price_book as pb

router = APIRouter(tags=["estimate-prices"])


def _estimate_or_404(db: Session, estimate_id: UUID) -> Estimate:
    row = db.get(Estimate, estimate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return row


def _sheet(db: Session, estimate: Estimate) -> EstimatePriceSheetRead:
    rows = pb.sheet_rows(db, estimate.id)
    return EstimatePriceSheetRead(
        estimate_id=estimate.id,
        rows=[EstimatePriceRead.model_validate(r) for r in rows],
        edited=sum(1 for r in rows if r.is_edited),
        pulled_at=max((r.pulled_at for r in rows), default=None),
        drift=PullResultRead(**pb.drift(db, estimate.id).as_dict()),
    )


def _recalc(db: Session, estimate: Estimate) -> None:
    from app.services.recalc import recalc_estimate

    recalc_estimate(db, estimate)


@router.get("/estimates/{estimate_id}/prices", response_model=EstimatePriceSheetRead)
def get_price_sheet(estimate_id: UUID, db: Session = Depends(get_db)) -> EstimatePriceSheetRead:
    return _sheet(db, _estimate_or_404(db, estimate_id))


@router.post("/estimates/{estimate_id}/prices/pull", response_model=PullResultRead)
def pull_price_sheet(
    estimate_id: UUID,
    dry_run: bool = Query(False, description="Preview what a pull would change without applying it."),
    db: Session = Depends(get_db),
) -> PullResultRead:
    """
    Pull the master list onto this sheet — the "button for updating" Chad asked
    for on 2026-08-30.

    Unedited rows follow the master list. **Edited rows are never overwritten**;
    they come back under `conflicts` with was / now / yours, and each is kept
    unless reset by hand. An unpriced master item is reported, not copied as
    zero.
    """
    estimate = _estimate_or_404(db, estimate_id)
    result = pb.pull_prices(db, estimate.id, apply=not dry_run)
    if not dry_run:
        _recalc(db, estimate)
        db.commit()
    return PullResultRead(**result.as_dict())


@router.patch("/estimates/{estimate_id}/prices/{price_id}", response_model=EstimatePriceRead)
def update_price(
    estimate_id: UUID,
    price_id: UUID,
    body: EstimatePriceUpdate,
    db: Session = Depends(get_db),
) -> EstimatePriceRead:
    estimate = _estimate_or_404(db, estimate_id)
    price = db.get(EstimatePrice, price_id)
    if price is None or price.estimate_id != estimate.id:
        raise HTTPException(status_code=404, detail="Price not on this estimate's sheet")
    try:
        pb.set_price(db, price, value=body.value, note=body.note, reset=body.reset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    _recalc(db, estimate)
    db.commit()
    db.refresh(price)
    return EstimatePriceRead.model_validate(price)
