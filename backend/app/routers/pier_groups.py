"""
Pier groups — the takeoff rows of a piers section (sql/037).

Thin over app.services.piers and app.services.pours-style bulk saving. The grid
save exists for the same reason paving's does: a piers section is a table, and
its forming, labor and equipment all key off the section totals, so writing a
field at a time would re-run all three on every keystroke.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import PIER_KINDS, EstimateSection
from app.models.mix_design import MixDesign
from app.models.pier_group import PierGroup
from app.schemas.pier_group import (
    PierDrillRateRead,
    PierGroupBulkResult,
    PierGroupBulkSave,
    PierGroupCreate,
    PierGroupRead,
    PierGroupUpdate,
    PierTotals,
)
from app.services.piers import refresh_section_pier_calcs, section_pier_totals

router = APIRouter(prefix="/pier-groups", tags=["pier-groups"])


def _to_read(db: Session, row: PierGroup) -> PierGroupRead:
    mix = db.get(MixDesign, row.mix_design_id) if row.mix_design_id else None
    data = {c.name: getattr(row, c.name) for c in PierGroup.__table__.columns}
    data["mix_design_code"] = mix.code if mix else None
    return PierGroupRead(**data)


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in PIER_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"section {section.name!r} is a {section.kind} section, not piers",
        )
    return section


def _recost(db: Session, section: EstimateSection) -> None:
    """
    Re-run the WHOLE section — geometry, forming, labor, equipment, cost.

    The three write paths below each used to call `refresh_section_pier_calcs`
    + `refresh_pour_costs` inline, which rewrites the geometry and reprices it
    while leaving the stored forming, labor and equipment on the pre-edit
    quantities. Only `/bulk` ran `recalc_section`.

    Piers is the assembly where that hurts most quietly: its superintendent days
    are TYPED rather than derived, and the whole rental ladder hangs off them,
    so a stale takeoff here is a stale fleet with correct-looking rates beside
    it. Same family as the zero-day ladder that came out $7,263.67 light.
    """
    from app.services.recalc import recalc_section

    recalc_section(db, section)


@router.get("/drill-rates", response_model=list[PierDrillRateRead])
def list_drill_rates(db: Session = Depends(get_db)) -> list[PierDrillRateRead]:
    """$/LF to drill and case, by shaft diameter."""
    rows = db.execute(
        text(
            "SELECT diameter_in, drill_per_lf, casing_per_lf, deduct_per_lf, note "
            "FROM pier_drill_rates ORDER BY diameter_in"
        )
    ).mappings().all()
    return [PierDrillRateRead(**r) for r in rows]


@router.get("", response_model=list[PierGroupRead])
def list_pier_groups(
    section_id: UUID = Query(..., description="Parent section"),
    db: Session = Depends(get_db),
) -> list[PierGroupRead]:
    stmt = (
        select(PierGroup)
        .where(PierGroup.section_id == section_id)
        .order_by(PierGroup.sort_order, PierGroup.created_at)
    )
    return [_to_read(db, r) for r in db.scalars(stmt).all()]


@router.get("/totals", response_model=PierTotals)
def pier_totals(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> PierTotals:
    _section_or_404(db, section_id)
    return PierTotals(section_id=section_id, **section_pier_totals(db, section_id))


@router.post("", response_model=PierGroupRead, status_code=status.HTTP_201_CREATED)
def create_pier_group(
    body: PierGroupCreate, db: Session = Depends(get_db)
) -> PierGroupRead:
    section = _section_or_404(db, body.section_id)
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    row = PierGroup(**body.model_dump())
    db.add(row)
    db.flush()
    # Section-wide, not just this row: under a drilling quote every group's
    # share is a fraction of the section's LF, so adding a pier group re-prices
    # the drilling on all of them.
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.put("/bulk", response_model=PierGroupBulkResult)
def bulk_save_pier_groups(
    body: PierGroupBulkSave, db: Session = Depends(get_db)
) -> PierGroupBulkResult:
    """
    Save a whole grid of pier groups in one request, then recalculate once.

    Rows the grid did not send are left alone unless delete_missing is set.
    """
    section = _section_or_404(db, body.section_id)

    existing = {
        r.id: r
        for r in db.scalars(
            select(PierGroup).where(PierGroup.section_id == body.section_id)
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
                    status_code=400, detail=f"pier group {incoming.id} is not in this section"
                )
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            if data.get("qty") is None or data.get("diameter_in") is None:
                raise HTTPException(
                    status_code=400,
                    detail="a new row needs at least qty and diameter_in",
                )
            row = PierGroup(section_id=body.section_id, **data)
            db.add(row)
            created += 1
        db.flush()
        seen.add(row.id)

    if body.delete_missing:
        for gid, row in existing.items():
            if gid not in seen:
                db.delete(row)
                deleted += 1
        db.flush()

    from app.services.recalc import recalc_section

    recalc_section(db, section)
    db.commit()

    rows = [
        _to_read(db, r)
        for r in db.scalars(
            select(PierGroup)
            .where(PierGroup.section_id == body.section_id)
            .order_by(PierGroup.sort_order, PierGroup.created_at)
        ).all()
    ]
    return PierGroupBulkResult(
        section_id=body.section_id,
        created=created,
        updated=updated,
        deleted=deleted,
        rows=rows,
        totals=PierTotals(
            section_id=body.section_id, **section_pier_totals(db, body.section_id)
        ),
    )


@router.get("/{group_id}", response_model=PierGroupRead)
def get_pier_group(group_id: UUID, db: Session = Depends(get_db)) -> PierGroupRead:
    row = db.get(PierGroup, group_id)
    if not row:
        raise HTTPException(status_code=404, detail="Pier group not found")
    return _to_read(db, row)


@router.patch("/{group_id}", response_model=PierGroupRead)
def update_pier_group(
    group_id: UUID, body: PierGroupUpdate, db: Session = Depends(get_db)
) -> PierGroupRead:
    row = db.get(PierGroup, group_id)
    if not row:
        raise HTTPException(status_code=404, detail="Pier group not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("mix_design_id") is not None and not db.get(MixDesign, data["mix_design_id"]):
        raise HTTPException(status_code=400, detail="mix_design_id not found")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)

    section = db.get(EstimateSection, row.section_id)
    # Changing this group's depth or count moves every other group's share of a
    # drilling quote, so the whole section is re-run.
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pier_group(group_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(PierGroup, group_id)
    if not row:
        raise HTTPException(status_code=404, detail="Pier group not found")
    sid = row.section_id
    db.delete(row)
    db.flush()

    section = db.get(EstimateSection, sid)
    if section is not None:
        # Deleting a group hands its share of a drilling quote to the others —
        # the lump does not shrink because you took a pier out of the takeoff.
        _recost(db, section)
    db.commit()
