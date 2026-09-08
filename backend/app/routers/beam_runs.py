"""
Beam runs — one separately poured beam type, or one continuous footing type
(sql/073). Mirrors routers/wall_runs.py, including its lesson: every write
path re-runs the WHOLE section, because a lump rebar quote is spread by
weight and the section's totals feed pumping, haul-off and the labor set.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.beam_run import BeamRun
from app.models.estimate_section import BEAM_KINDS, EstimateSection
from app.models.mix_design import MixDesign
from app.schemas.beam_run import (
    BeamRunBulkResult,
    BeamRunBulkSave,
    BeamRunCreate,
    BeamRunRead,
    BeamRunUpdate,
    BeamTotals,
)
from app.services.beams import section_beam_totals

router = APIRouter(prefix="/beam-runs", tags=["beam-runs"])


def _to_read(row: BeamRun) -> BeamRunRead:
    return BeamRunRead.model_validate(row)


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in BEAM_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Section {section.name!r} is a {section.kind} section, not grade beams",
        )
    return section


def _recost(db: Session, section: EstimateSection) -> None:
    from app.services.recalc import recalc_section

    recalc_section(db, section)


def _check_mix(db: Session, mix_id: int | None) -> None:
    if mix_id is not None and not db.get(MixDesign, mix_id):
        raise HTTPException(status_code=400, detail=f"mix_design_id {mix_id} not found")


@router.get("", response_model=list[BeamRunRead])
def list_beam_runs(section_id: UUID = Query(...), db: Session = Depends(get_db)) -> list[BeamRunRead]:
    rows = db.scalars(
        select(BeamRun).where(BeamRun.section_id == section_id).order_by(BeamRun.sort_order, BeamRun.created_at)
    ).all()
    return [_to_read(r) for r in rows]


@router.get("/totals", response_model=BeamTotals)
def beam_totals(section_id: UUID = Query(...), db: Session = Depends(get_db)) -> BeamTotals:
    return BeamTotals(section_id=section_id, **section_beam_totals(db, section_id))


@router.post("", response_model=BeamRunRead, status_code=status.HTTP_201_CREATED)
def create_beam_run(body: BeamRunCreate, db: Session = Depends(get_db)) -> BeamRunRead:
    section = _section_or_404(db, body.section_id)
    _check_mix(db, body.mix_design_id)
    row = BeamRun(**body.model_dump())
    db.add(row)
    db.flush()
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(row)


@router.put("/bulk", response_model=BeamRunBulkResult)
def bulk_save_beam_runs(body: BeamRunBulkSave, db: Session = Depends(get_db)) -> BeamRunBulkResult:
    """Save a whole grid in one request, then recalculate the section once."""
    section = _section_or_404(db, body.section_id)

    existing = {r.id: r for r in db.scalars(select(BeamRun).where(BeamRun.section_id == body.section_id)).all()}
    created = updated = deleted = 0
    seen: set[UUID] = set()

    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id"})
        _check_mix(db, data.get("mix_design_id"))
        data.setdefault("sort_order", order * 10)

        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(status_code=400, detail=f"beam run {incoming.id} is not in this section")
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            if not data.get("length_ft"):
                raise HTTPException(status_code=400, detail="a new row needs at least a length")
            row = BeamRun(section_id=body.section_id, **data)
            db.add(row)
            created += 1
        db.flush()
        seen.add(row.id)

    if body.delete_missing:
        for rid, row in existing.items():
            if rid not in seen:
                db.delete(row)
                deleted += 1
        db.flush()

    _recost(db, section)
    db.commit()

    rows = [
        _to_read(r)
        for r in db.scalars(
            select(BeamRun).where(BeamRun.section_id == body.section_id).order_by(BeamRun.sort_order, BeamRun.created_at)
        ).all()
    ]
    return BeamRunBulkResult(
        section_id=body.section_id,
        created=created,
        updated=updated,
        deleted=deleted,
        rows=rows,
        totals=BeamTotals(section_id=body.section_id, **section_beam_totals(db, body.section_id)),
    )


@router.get("/{run_id}", response_model=BeamRunRead)
def get_beam_run(run_id: UUID, db: Session = Depends(get_db)) -> BeamRunRead:
    row = db.get(BeamRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Beam run not found")
    return _to_read(row)


@router.patch("/{run_id}", response_model=BeamRunRead)
def update_beam_run(run_id: UUID, body: BeamRunUpdate, db: Session = Depends(get_db)) -> BeamRunRead:
    row = db.get(BeamRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Beam run not found")
    data = body.model_dump(exclude_unset=True)
    _check_mix(db, data.get("mix_design_id"))
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)

    section = db.get(EstimateSection, row.section_id)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(row)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_beam_run(run_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(BeamRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Beam run not found")
    sid = row.section_id
    db.delete(row)
    db.flush()
    section = db.get(EstimateSection, sid)
    if section is not None:
        _recost(db, section)
    db.commit()
