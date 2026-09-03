"""
Column types — one column and how many of it (sql/045).

Mirrors routers/wall_runs.py, including the rule learned on piers and repeated
on walls: every write path re-runs the WHOLE section rather than the single row
it touched. Here there are two reasons and both bite. A lump rebar quote is
spread across types by weight, and — the one specific to columns — the
supervision duration is derived from the total column COUNT, so changing the
quantity on one type moves the superintendent, the foreman, the expense
allowance, the PM and the entire rental ladder for every other type on the
section. A per-row refresh would leave all of that stale.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.column_type import ColumnType
from app.models.estimate_section import COLUMN_KINDS, EstimateSection
from app.models.mix_design import MixDesign
from app.schemas.column_type import (
    ColumnTotals,
    ColumnTypeBulkResult,
    ColumnTypeBulkSave,
    ColumnTypeCreate,
    ColumnTypeRead,
    ColumnTypeUpdate,
)
from app.services.columns import refresh_section_column_calcs, section_column_totals

router = APIRouter(prefix="/column-types", tags=["column-types"])


def _to_read(db: Session, row: ColumnType) -> ColumnTypeRead:
    return ColumnTypeRead.model_validate(row)


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in COLUMN_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Section {section.name!r} is a {section.kind} section, not columns",
        )
    return section


def _recost(db: Session, section: EstimateSection) -> None:
    """
    Re-run the WHOLE section — geometry, forming, labor, equipment, cost.

    The module docstring above says every write path re-runs the whole section
    *because* supervision derives from the column COUNT. Until 2026-09-02 this
    function did not: it refreshed the geometry and repriced it, leaving the
    stored labor and equipment on the previous count.

    PATCHing one type's qty from 38 to 400 left the superintendent on **17
    days** where 400 columns demand 107.5, and the section at $400,576.92
    against a correct $837,403.34 — **$436,826.42 light**, with the rental
    ladder stale behind it. `/bulk` called `recalc_section` and was right; the
    single-row paths beside it were not.
    """
    from app.services.recalc import recalc_section

    recalc_section(db, section)


@router.get("", response_model=list[ColumnTypeRead])
def list_column_types(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> list[ColumnTypeRead]:
    rows = db.scalars(
        select(ColumnType)
        .where(ColumnType.section_id == section_id)
        .order_by(ColumnType.sort_order, ColumnType.created_at)
    ).all()
    return [_to_read(db, r) for r in rows]


@router.get("/totals", response_model=ColumnTotals)
def column_totals(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> ColumnTotals:
    return ColumnTotals(section_id=section_id, **section_column_totals(db, section_id))


@router.post("", response_model=ColumnTypeRead, status_code=status.HTTP_201_CREATED)
def create_column_type(
    body: ColumnTypeCreate, db: Session = Depends(get_db)
) -> ColumnTypeRead:
    section = _section_or_404(db, body.section_id)
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    row = ColumnType(**body.model_dump())
    db.add(row)
    db.flush()
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.put("/bulk", response_model=ColumnTypeBulkResult)
def bulk_save_column_types(
    body: ColumnTypeBulkSave, db: Session = Depends(get_db)
) -> ColumnTypeBulkResult:
    """Save a whole grid in one request, then recalculate the section once."""
    section = _section_or_404(db, body.section_id)

    existing = {
        r.id: r
        for r in db.scalars(
            select(ColumnType).where(ColumnType.section_id == body.section_id)
        ).all()
    }
    created = updated = deleted = 0
    seen: set[UUID] = set()

    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id"})
        mix_id = data.get("mix_design_id")
        if mix_id is not None and not db.get(MixDesign, mix_id):
            raise HTTPException(
                status_code=400, detail=f"mix_design_id {mix_id} not found"
            )
        data.setdefault("sort_order", order * 10)

        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"column type {incoming.id} is not in this section",
                )
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            # A column with no height is not a column. Quantity alone is not
            # enough either — the takeoff needs something to measure.
            if not data.get("height_ft"):
                raise HTTPException(
                    status_code=400, detail="a new row needs at least a height"
                )
            row = ColumnType(section_id=body.section_id, **data)
            db.add(row)
            created += 1
        db.flush()
        seen.add(row.id)

    # Rows the grid did not send are LEFT ALONE unless delete_missing is set.
    # The grid scrolls and a request can be truncated; neither should cost a
    # column type.
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
            select(ColumnType)
            .where(ColumnType.section_id == body.section_id)
            .order_by(ColumnType.sort_order, ColumnType.created_at)
        ).all()
    ]
    return ColumnTypeBulkResult(
        section_id=body.section_id,
        created=created,
        updated=updated,
        deleted=deleted,
        rows=rows,
        totals=ColumnTotals(
            section_id=body.section_id, **section_column_totals(db, body.section_id)
        ),
    )


@router.get("/{type_id}", response_model=ColumnTypeRead)
def get_column_type(type_id: UUID, db: Session = Depends(get_db)) -> ColumnTypeRead:
    row = db.get(ColumnType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Column type not found")
    return _to_read(db, row)


@router.patch("/{type_id}", response_model=ColumnTypeRead)
def update_column_type(
    type_id: UUID, body: ColumnTypeUpdate, db: Session = Depends(get_db)
) -> ColumnTypeRead:
    row = db.get(ColumnType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Column type not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("mix_design_id") is not None and not db.get(
        MixDesign, data["mix_design_id"]
    ):
        raise HTTPException(status_code=400, detail="mix_design_id not found")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)

    section = db.get(EstimateSection, row.section_id)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_column_type(type_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(ColumnType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Column type not found")
    section = db.get(EstimateSection, row.section_id)
    db.delete(row)
    db.flush()
    if section is not None:
        _recost(db, section)
    db.commit()
