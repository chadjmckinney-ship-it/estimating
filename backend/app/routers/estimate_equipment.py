from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.schemas.estimate_equipment import (
    EstimateEquipmentLineUpdate,
    EstimateEquipmentRead,
)
from app.services.estimate_equipment import (
    get_or_refresh_equipment,
    refresh_and_store_equipment,
    update_equipment_line,
)

router = APIRouter(tags=["estimate-equipment"])


def _to_read(estimate_id: UUID, data: dict) -> EstimateEquipmentRead:
    return EstimateEquipmentRead(estimate_id=estimate_id, **data)


@router.get(
    "/estimates/{estimate_id}/equipment",
    response_model=EstimateEquipmentRead,
)
def get_estimate_equipment(
    estimate_id: UUID, db: Session = Depends(get_db)
) -> EstimateEquipmentRead:
    """Stored equipment + contract services. Auto-saves on first open."""
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    return _to_read(estimate_id, get_or_refresh_equipment(db, estimate_id))


@router.post(
    "/estimates/{estimate_id}/equipment/refresh",
    response_model=EstimateEquipmentRead,
)
def refresh_estimate_equipment(
    estimate_id: UUID, db: Session = Depends(get_db)
) -> EstimateEquipmentRead:
    """Recalculate days from super ladder + pour CY; keeps manual lines."""
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    return _to_read(estimate_id, refresh_and_store_equipment(db, estimate_id))


@router.patch(
    "/estimates/{estimate_id}/equipment/lines/{code}",
    response_model=EstimateEquipmentRead,
)
def patch_equipment_line(
    estimate_id: UUID,
    code: str,
    body: EstimateEquipmentLineUpdate,
    db: Session = Depends(get_db),
) -> EstimateEquipmentRead:
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    try:
        data = update_equipment_line(
            db,
            estimate_id,
            code,
            enabled=body.enabled,
            rate=body.rate,
            days_qty=body.days_qty,
            mark_manual=body.mark_manual,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _to_read(estimate_id, data)
