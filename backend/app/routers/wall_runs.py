"""
Wall runs — one wall type and the footing under it (sql/040).

Mirrors routers/pier_groups.py, including the lesson learned there: every write
path re-runs the WHOLE section rather than the single row it touched. On piers
that was because a drilling quote is spread across groups; here it is because a
lump rebar quote is spread by weight, and because the section's totals feed
pumping and the labor set. Either way, a per-row refresh leaves the rest of the
section holding stale shares.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import WALL_KINDS, EstimateSection
from app.models.mix_design import MixDesign
from app.models.wall_run import WallRun
from app.schemas.wall_run import (
    WallRunBulkResult,
    WallRunBulkSave,
    WallRunCreate,
    WallRunRead,
    WallRunUpdate,
    WallTotals,
)
from app.services.walls import refresh_section_wall_calcs, section_wall_totals

router = APIRouter(prefix="/wall-runs", tags=["wall-runs"])


def _to_read(db: Session, row: WallRun) -> WallRunRead:
    return WallRunRead.model_validate(row)


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in WALL_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Section {section.name!r} is a {section.kind} section, not walls",
        )
    return section


def _recost(db: Session, section: EstimateSection) -> None:
    """
    Re-run the WHOLE section — geometry, forming, labor, equipment, cost.

    This used to be `refresh_section_wall_calcs` + `refresh_pour_costs`, which
    rewrites the geometry and reprices it while leaving the three stored
    takeoffs on the quantities they had before the edit. Only `/bulk` called
    `recalc_section`, so a grid save was correct and the single-row POST, PATCH
    and DELETE beside it were not.

    Measured on columns, where it is worst because supervision derives from the
    column count: PATCHing one type's qty from 38 to 400 left the superintendent
    on 17 days against the 107.5 the count demands, and the section
    $436,826.42 light. On walls, decupling a run's length left the forming
    package and the labor untouched.

    The extra work is the two takeoff refreshes. That is the same work `/bulk`
    has always done for the same edit, so nothing here is newly expensive — the
    cheap path was simply wrong.
    """
    from app.services.recalc import recalc_section

    recalc_section(db, section)


@router.get("", response_model=list[WallRunRead])
def list_wall_runs(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> list[WallRunRead]:
    rows = db.scalars(
        select(WallRun)
        .where(WallRun.section_id == section_id)
        .order_by(WallRun.sort_order, WallRun.created_at)
    ).all()
    return [_to_read(db, r) for r in rows]


@router.get("/totals", response_model=WallTotals)
def wall_totals(section_id: UUID = Query(...), db: Session = Depends(get_db)) -> WallTotals:
    return WallTotals(section_id=section_id, **section_wall_totals(db, section_id))


@router.post("", response_model=WallRunRead, status_code=status.HTTP_201_CREATED)
def create_wall_run(body: WallRunCreate, db: Session = Depends(get_db)) -> WallRunRead:
    section = _section_or_404(db, body.section_id)
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    row = WallRun(**body.model_dump())
    db.add(row)
    db.flush()
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.put("/bulk", response_model=WallRunBulkResult)
def bulk_save_wall_runs(
    body: WallRunBulkSave, db: Session = Depends(get_db)
) -> WallRunBulkResult:
    """Save a whole grid in one request, then recalculate the section once."""
    section = _section_or_404(db, body.section_id)

    existing = {
        r.id: r
        for r in db.scalars(
            select(WallRun).where(WallRun.section_id == body.section_id)
        ).all()
    }
    created = updated = deleted = 0
    seen: set[UUID] = set()

    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id"})
        mix_id = data.get("mix_design_id")
        if mix_id is not None and not db.get(MixDesign, mix_id):
            raise HTTPException(status_code=400, detail=f"mix_design_id {mix_id} not found")
        data.setdefault("sort_order", order * 10)

        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"wall run {incoming.id} is not in this section",
                )
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            if not data.get("length_ft"):
                raise HTTPException(
                    status_code=400, detail="a new row needs at least a length"
                )
            row = WallRun(section_id=body.section_id, **data)
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

    from app.services.recalc import recalc_section

    recalc_section(db, section)
    db.commit()

    rows = [
        _to_read(db, r)
        for r in db.scalars(
            select(WallRun)
            .where(WallRun.section_id == body.section_id)
            .order_by(WallRun.sort_order, WallRun.created_at)
        ).all()
    ]
    return WallRunBulkResult(
        section_id=body.section_id,
        created=created,
        updated=updated,
        deleted=deleted,
        rows=rows,
        totals=WallTotals(
            section_id=body.section_id, **section_wall_totals(db, body.section_id)
        ),
    )


@router.get("/{run_id}", response_model=WallRunRead)
def get_wall_run(run_id: UUID, db: Session = Depends(get_db)) -> WallRunRead:
    row = db.get(WallRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Wall run not found")
    return _to_read(db, row)


@router.patch("/{run_id}", response_model=WallRunRead)
def update_wall_run(
    run_id: UUID, body: WallRunUpdate, db: Session = Depends(get_db)
) -> WallRunRead:
    row = db.get(WallRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Wall run not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("mix_design_id") is not None and not db.get(MixDesign, data["mix_design_id"]):
        raise HTTPException(status_code=400, detail="mix_design_id not found")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)

    section = db.get(EstimateSection, row.section_id)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wall_run(run_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(WallRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Wall run not found")
    sid = row.section_id
    db.delete(row)
    db.flush()
    section = db.get(EstimateSection, sid)
    if section is not None:
        _recost(db, section)
    db.commit()
