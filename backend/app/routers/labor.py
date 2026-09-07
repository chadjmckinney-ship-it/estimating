from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import EstimateSection
from app.schemas.labor import LaborLineUpdate, LaborMaterialsRead
from app.services.labor import (
    get_or_refresh_labor,
    refresh_and_store_labor,
    update_labor_line,
)

router = APIRouter(tags=["labor"])


def _to_read(section_id: UUID, data: dict) -> LaborMaterialsRead:
    return LaborMaterialsRead(section_id=section_id, **data)


@router.get(
    "/sections/{section_id}/labor",
    response_model=LaborMaterialsRead,
)
def get_labor(section_id: UUID, db: Session = Depends(get_db)) -> LaborMaterialsRead:
    """Stored slab labor + supervision. Auto-saves on first open."""
    if not db.get(EstimateSection, section_id):
        raise HTTPException(status_code=404, detail="Section not found")
    return _to_read(section_id, get_or_refresh_labor(db, section_id))


@router.post(
    "/sections/{section_id}/labor/refresh",
    response_model=LaborMaterialsRead,
)
def refresh_labor(section_id: UUID, db: Session = Depends(get_db)) -> LaborMaterialsRead:
    """Recalculate qty from pours; keeps manual rates/qty where marked."""
    if not db.get(EstimateSection, section_id):
        raise HTTPException(status_code=404, detail="Section not found")
    return _to_read(section_id, refresh_and_store_labor(db, section_id))


@router.patch(
    "/sections/{section_id}/labor/lines/{code}",
    response_model=LaborMaterialsRead,
)
def patch_labor_line(
    section_id: UUID,
    code: str,
    body: LaborLineUpdate,
    db: Session = Depends(get_db),
) -> LaborMaterialsRead:
    """Update rate, qty, or enabled (Y/N) on one labor/supervision line."""
    if not db.get(EstimateSection, section_id):
        raise HTTPException(status_code=404, detail="Section not found")
    try:
        data = update_labor_line(
            db,
            section_id,
            code,
            enabled=body.enabled,
            rate=body.rate,
            qty=body.qty,
            mark_manual=body.mark_manual,
        )
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 400, detail=str(e)) from e
    return _to_read(section_id, data)
