from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.estimator import Estimator
from app.models.project import Project
from app.schemas.estimate import EstimateCreate, EstimateRead, EstimateUpdate

router = APIRouter(prefix="/estimates", tags=["estimates"])

# Estimate-level inputs that feed the stored pour calc_* columns.
# waste_rebar is here because it carries the slab mat's lap allowance.
_POUR_CALC_FIELDS = frozenset({"waste_concrete", "waste_sand", "waste_rebar"})


def _recalc_after_estimate_change(db: Session, row: Estimate, changed: set[str]) -> None:
    """
    Re-derive everything downstream of a changed estimate input.

    The calc_* columns and the forming/labor/equipment lines are all stored, so
    an estimate edit that isn't propagated leaves the UI showing new factors over
    stale numbers. Only refreshes takeoffs that were already saved — opening an
    estimate is what creates them, and this shouldn't do it as a side effect.
    """
    from app.services.recalc import recalc_estimate

    pours = bool(changed & _POUR_CALC_FIELDS)
    # A pour change ripples outward: rebar feeds forming accessories and labor
    # tie steel, concrete CY feeds equipment pumping.
    if pours:
        recalc_estimate(db, row)
    elif "form_percent" in changed:
        # form_percent scales the form lumber lines only.
        recalc_estimate(db, row, pours=False, labor=False, equipment=False)


def _to_read(db: Session, row: Estimate) -> EstimateRead:
    project = db.get(Project, row.project_id)
    estimator = db.get(Estimator, row.estimator_id) if row.estimator_id else None
    return EstimateRead(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        status=row.status,
        estimator_id=row.estimator_id,
        version=row.version,
        waste_concrete=row.waste_concrete,
        waste_sand=row.waste_sand,
        waste_rebar=row.waste_rebar,
        form_percent=row.form_percent,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
        project_name=project.name if project else None,
        estimator_name=estimator.full_name if estimator else None,
    )


@router.get("", response_model=list[EstimateRead])
def list_estimates(
    project_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[EstimateRead]:
    stmt = select(Estimate).order_by(Estimate.updated_at.desc())
    if project_id:
        stmt = stmt.where(Estimate.project_id == project_id)
    if status_filter:
        stmt = stmt.where(Estimate.status == status_filter)
    return [_to_read(db, r) for r in db.scalars(stmt).all()]


@router.get("/{estimate_id}", response_model=EstimateRead)
def get_estimate(estimate_id: UUID, db: Session = Depends(get_db)) -> EstimateRead:
    row = db.get(Estimate, estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return _to_read(db, row)


@router.post("", response_model=EstimateRead, status_code=status.HTTP_201_CREATED)
def create_estimate(body: EstimateCreate, db: Session = Depends(get_db)) -> EstimateRead:
    if not db.get(Project, body.project_id):
        raise HTTPException(status_code=400, detail="project_id not found")
    if body.estimator_id and not db.get(Estimator, body.estimator_id):
        raise HTTPException(status_code=400, detail="estimator_id not found")
    row = Estimate(
        project_id=body.project_id,
        name=body.name.strip(),
        status=body.status.value,
        estimator_id=body.estimator_id,
        version=body.version,
        waste_concrete=body.waste_concrete,
        waste_sand=body.waste_sand,
        waste_rebar=body.waste_rebar,
        form_percent=body.form_percent,
        notes=body.notes,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Estimate with this project/name/version already exists",
        ) from None
    db.refresh(row)
    return _to_read(db, row)


@router.patch("/{estimate_id}", response_model=EstimateRead)
def update_estimate(
    estimate_id: UUID, body: EstimateUpdate, db: Session = Depends(get_db)
) -> EstimateRead:
    row = db.get(Estimate, estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "estimator_id" in data and data["estimator_id"] is not None:
        if not db.get(Estimator, data["estimator_id"]):
            raise HTTPException(status_code=400, detail="estimator_id not found")
    changed = {k for k, v in data.items() if getattr(row, k) != v}
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.flush()
        _recalc_after_estimate_change(db, row, changed)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict updating estimate") from None
    db.refresh(row)
    return _to_read(db, row)


@router.post("/{estimate_id}/recalc", response_model=EstimateRead)
def recalc_estimate_endpoint(
    estimate_id: UUID, db: Session = Depends(get_db)
) -> EstimateRead:
    """
    Rewrite this estimate's pours and stored takeoffs from current inputs.

    Use after changing company defaults, or any time the numbers look stale.
    Takeoffs that were never opened stay uncreated.
    """
    from app.services.recalc import recalc_estimate

    row = db.get(Estimate, estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    recalc_estimate(db, row)
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_estimate(estimate_id: UUID, db: Session = Depends(get_db)) -> None:
    """Permanently delete estimate (cascades mono slabs, grade beams, bids)."""
    row = db.get(Estimate, estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    db.delete(row)
    db.commit()
