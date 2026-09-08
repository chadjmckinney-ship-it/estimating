"""
Miscellaneous items — priced site items on a miscellaneous section (sql/078).

Mirrors routers/panel_types.py: every write path re-runs the whole section,
and a grid saves in one request. The four family grids on the page each
send only their own rows, so `delete_missing` stays off and the other three
families are left alone.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import MISC_KINDS, EstimateSection
from app.models.misc_item import MiscItem
from app.models.mix_design import MixDesign
from app.schemas.misc_item import (
    MiscItemBulkResult,
    MiscItemBulkSave,
    MiscItemCreate,
    MiscItemRead,
    MiscItemUpdate,
    MiscTotals,
)
from app.services.misc import section_misc_totals

router = APIRouter(prefix="/misc-items", tags=["misc-items"])


def _to_read(db: Session, row: MiscItem) -> MiscItemRead:
    return MiscItemRead.model_validate(row)


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in MISC_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Section {section.name!r} is a {section.kind} section, not miscellaneous",
        )
    return section


def _recost(db: Session, section: EstimateSection) -> None:
    from app.services.recalc import recalc_section

    recalc_section(db, section)


@router.get("", response_model=list[MiscItemRead])
def list_misc_items(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> list[MiscItemRead]:
    rows = db.scalars(
        select(MiscItem)
        .where(MiscItem.section_id == section_id)
        .order_by(MiscItem.sort_order, MiscItem.created_at)
    ).all()
    return [_to_read(db, r) for r in rows]


@router.get("/totals", response_model=MiscTotals)
def misc_totals(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> MiscTotals:
    return MiscTotals(section_id=section_id, **section_misc_totals(db, section_id))


@router.post("", response_model=MiscItemRead, status_code=status.HTTP_201_CREATED)
def create_misc_item(body: MiscItemCreate, db: Session = Depends(get_db)) -> MiscItemRead:
    section = _section_or_404(db, body.section_id)
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")
    row = MiscItem(**body.model_dump())
    db.add(row)
    db.flush()
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.put("/bulk", response_model=MiscItemBulkResult)
def bulk_save_misc_items(body: MiscItemBulkSave, db: Session = Depends(get_db)) -> MiscItemBulkResult:
    """Save one family's grid in one request, then recalculate the section once."""
    section = _section_or_404(db, body.section_id)

    existing = {
        r.id: r
        for r in db.scalars(select(MiscItem).where(MiscItem.section_id == body.section_id)).all()
    }
    created = updated = deleted = 0
    seen: set[UUID] = set()

    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id"})
        mix_id = data.get("mix_design_id")
        if mix_id is not None and not db.get(MixDesign, mix_id):
            raise HTTPException(status_code=400, detail=f"mix_design_id {mix_id} not found")

        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(
                    status_code=400, detail=f"misc item {incoming.id} is not in this section"
                )
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            # A new row lands after the family's last, so the grids keep their order.
            if "sort_order" not in data:
                last = max(
                    (r.sort_order for r in existing.values() if r.shape == data.get("shape", "round")),
                    default=0,
                )
                data["sort_order"] = last + 10 + order
            row = MiscItem(section_id=body.section_id, **data)
            db.add(row)
            created += 1
        db.flush()
        seen.add(row.id)

    # Rows the grid did not send are LEFT ALONE unless delete_missing is set —
    # the other three families' rows above all.
    if body.delete_missing:
        for rid, row in existing.items():
            if rid not in seen:
                db.delete(row)
                deleted += 1
        db.flush()

    _recost(db, section)
    db.commit()

    rows = [
        _to_read(db, r)
        for r in db.scalars(
            select(MiscItem)
            .where(MiscItem.section_id == body.section_id)
            .order_by(MiscItem.sort_order, MiscItem.created_at)
        ).all()
    ]
    return MiscItemBulkResult(
        section_id=body.section_id, created=created, updated=updated, deleted=deleted, rows=rows,
        totals=MiscTotals(section_id=body.section_id, **section_misc_totals(db, body.section_id, section)),
    )


@router.get("/{item_id}", response_model=MiscItemRead)
def get_misc_item(item_id: UUID, db: Session = Depends(get_db)) -> MiscItemRead:
    row = db.get(MiscItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Misc item not found")
    return _to_read(db, row)


@router.patch("/{item_id}", response_model=MiscItemRead)
def update_misc_item(item_id: UUID, body: MiscItemUpdate, db: Session = Depends(get_db)) -> MiscItemRead:
    row = db.get(MiscItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Misc item not found")
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


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_misc_item(item_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(MiscItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Misc item not found")
    section = db.get(EstimateSection, row.section_id)
    db.delete(row)
    db.flush()
    if section is not None:
        _recost(db, section)
    db.commit()
