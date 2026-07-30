from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.schemas.forming import FormingMaterialsRead, FormPercentUpdate
from app.services.forming import (
    get_or_refresh_forming,
    refresh_and_store_forming,
    set_form_percent_and_refresh,
)

router = APIRouter(tags=["forming"])


def _to_read(estimate_id: UUID, data: dict) -> FormingMaterialsRead:
    return FormingMaterialsRead(estimate_id=estimate_id, **data)


@router.get(
    "/estimates/{estimate_id}/forming-materials",
    response_model=FormingMaterialsRead,
)
def get_forming_materials(
    estimate_id: UUID, db: Session = Depends(get_db)
) -> FormingMaterialsRead:
    """
    Stored forming / lumber takeoff for an estimate.
    If never refreshed, calculates from pours and saves to
    estimate_forming_lines + estimate_forming_summary.
    """
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    data = get_or_refresh_forming(db, estimate_id)
    return _to_read(estimate_id, data)


@router.post(
    "/estimates/{estimate_id}/forming-materials/refresh",
    response_model=FormingMaterialsRead,
    status_code=status.HTTP_200_OK,
)
def refresh_forming_materials(
    estimate_id: UUID, db: Session = Depends(get_db)
) -> FormingMaterialsRead:
    """Recalculate from current pours and overwrite stored non-manual lines."""
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    data = refresh_and_store_forming(db, estimate_id)
    return _to_read(estimate_id, data)


@router.put(
    "/estimates/{estimate_id}/forming-materials/form-percent",
    response_model=FormingMaterialsRead,
)
def update_form_percent(
    estimate_id: UUID,
    body: FormPercentUpdate,
    db: Session = Depends(get_db),
) -> FormingMaterialsRead:
    """
    Set % of forming on this estimate and recalculate form lumber only
    (2x4, 2x6, 2x10, forming ply, masonite). Nails/anchors/bracing/etc. unchanged by form%.
    """
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    try:
        data = set_form_percent_and_refresh(db, estimate_id, Decimal(body.form_percent))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _to_read(estimate_id, data)
