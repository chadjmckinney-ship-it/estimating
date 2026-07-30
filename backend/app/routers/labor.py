from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.schemas.labor import LaborLineUpdate, LaborMaterialsRead
from app.services.labor import (
    get_or_refresh_labor,
    refresh_and_store_labor,
    update_labor_line,
)

router = APIRouter(tags=["labor"])


def _to_read(estimate_id: UUID, data: dict) -> LaborMaterialsRead:
    return LaborMaterialsRead(estimate_id=estimate_id, **data)


@router.get(
    "/estimates/{estimate_id}/labor",
    response_model=LaborMaterialsRead,
)
def get_labor(estimate_id: UUID, db: Session = Depends(get_db)) -> LaborMaterialsRead:
    """Stored slab labor + supervision. Auto-saves on first open."""
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    return _to_read(estimate_id, get_or_refresh_labor(db, estimate_id))


@router.post(
    "/estimates/{estimate_id}/labor/refresh",
    response_model=LaborMaterialsRead,
)
def refresh_labor(estimate_id: UUID, db: Session = Depends(get_db)) -> LaborMaterialsRead:
    """Recalculate qty from pours; keeps manual rates/qty where marked."""
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    return _to_read(estimate_id, refresh_and_store_labor(db, estimate_id))


@router.patch(
    "/estimates/{estimate_id}/labor/lines/{code}",
    response_model=LaborMaterialsRead,
)
def patch_labor_line(
    estimate_id: UUID,
    code: str,
    body: LaborLineUpdate,
    db: Session = Depends(get_db),
) -> LaborMaterialsRead:
    """Update rate, qty, or enabled (Y/N) on one labor/supervision line."""
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    try:
        data = update_labor_line(
            db,
            estimate_id,
            code,
            enabled=body.enabled,
            rate=body.rate,
            qty=body.qty,
            mark_manual=body.mark_manual,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _to_read(estimate_id, data)
