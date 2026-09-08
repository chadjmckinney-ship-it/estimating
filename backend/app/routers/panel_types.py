"""
Panel types — one tilt-wall panel and how many of it (sql/077).

Mirrors routers/column_types.py, including its rule: every write path re-runs
the WHOLE section. A lump rebar quote is spread across types by weight, the
lifting and bracing inserts count every panel, the engineering line counts
the types, and the equipment ladder rides typed supervision days — so one
type's quantity moves numbers on every other row.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import PANEL_KINDS, EstimateSection
from app.models.mix_design import MixDesign
from app.models.panel_type import PanelType
from app.schemas.panel_type import (
    PanelTotals,
    PanelTypeBulkResult,
    PanelTypeBulkSave,
    PanelTypeCreate,
    PanelTypeRead,
    PanelTypeUpdate,
)
from app.services.panels import refresh_section_panel_calcs, section_panel_totals

router = APIRouter(prefix="/panel-types", tags=["panel-types"])

_Q4 = Decimal("0.0001")


def _d(x) -> Decimal:
    return Decimal(str(x)) if x is not None and x != "" else Decimal("0")


def _to_read(db: Session, row: PanelType) -> PanelTypeRead:
    out = PanelTypeRead.model_validate(row)
    # The tab's X column: what one panel of this type costs. Derived here
    # rather than stored, because it is the type's cost over its count and
    # nothing else reads it.
    n = Decimal(int(row.qty or 0))
    if n > 0 and row.calc_cost is not None:
        out.calc_cost_per_panel = (_d(row.calc_cost) / n).quantize(_Q4)
        out.calc_sale_per_panel = (_d(row.calc_sale) / n).quantize(_Q4)
    return out


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in PANEL_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Section {section.name!r} is a {section.kind} section, not panels",
        )
    return section


def _recost(db: Session, section: EstimateSection) -> None:
    """Re-run the WHOLE section — geometry, forming, labor, equipment, cost."""
    from app.services.recalc import recalc_section

    recalc_section(db, section)


def _check_new_row(data: dict) -> None:
    """A panel needs a length and a height — the two things every quantity here multiplies."""
    if not data.get("length_ft"):
        raise HTTPException(status_code=400, detail="a new row needs a length")
    if _d(data.get("top_el_ft")) - _d(data.get("bot_el_ft")) <= 0:
        raise HTTPException(
            status_code=400,
            detail="a new row needs a top elevation above its bottom elevation",
        )


@router.get("", response_model=list[PanelTypeRead])
def list_panel_types(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> list[PanelTypeRead]:
    rows = db.scalars(
        select(PanelType)
        .where(PanelType.section_id == section_id)
        .order_by(PanelType.sort_order, PanelType.created_at)
    ).all()
    return [_to_read(db, r) for r in rows]


@router.get("/totals", response_model=PanelTotals)
def panel_totals(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> PanelTotals:
    return PanelTotals(section_id=section_id, **section_panel_totals(db, section_id))


@router.post("", response_model=PanelTypeRead, status_code=status.HTTP_201_CREATED)
def create_panel_type(
    body: PanelTypeCreate, db: Session = Depends(get_db)
) -> PanelTypeRead:
    section = _section_or_404(db, body.section_id)
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    row = PanelType(**body.model_dump())
    db.add(row)
    db.flush()
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.put("/bulk", response_model=PanelTypeBulkResult)
def bulk_save_panel_types(
    body: PanelTypeBulkSave, db: Session = Depends(get_db)
) -> PanelTypeBulkResult:
    """Save a whole grid in one request, then recalculate the section once."""
    section = _section_or_404(db, body.section_id)

    existing = {
        r.id: r
        for r in db.scalars(
            select(PanelType).where(PanelType.section_id == body.section_id)
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
                    detail=f"panel type {incoming.id} is not in this section",
                )
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            _check_new_row(data)
            row = PanelType(section_id=body.section_id, **data)
            db.add(row)
            created += 1
        db.flush()
        seen.add(row.id)

    # Rows the grid did not send are LEFT ALONE unless delete_missing is set.
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
            select(PanelType)
            .where(PanelType.section_id == body.section_id)
            .order_by(PanelType.sort_order, PanelType.created_at)
        ).all()
    ]
    return PanelTypeBulkResult(
        section_id=body.section_id,
        created=created,
        updated=updated,
        deleted=deleted,
        rows=rows,
        totals=PanelTotals(
            section_id=body.section_id, **section_panel_totals(db, body.section_id)
        ),
    )


@router.get("/{type_id}", response_model=PanelTypeRead)
def get_panel_type(type_id: UUID, db: Session = Depends(get_db)) -> PanelTypeRead:
    row = db.get(PanelType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Panel type not found")
    return _to_read(db, row)


@router.patch("/{type_id}", response_model=PanelTypeRead)
def update_panel_type(
    type_id: UUID, body: PanelTypeUpdate, db: Session = Depends(get_db)
) -> PanelTypeRead:
    row = db.get(PanelType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Panel type not found")
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
def delete_panel_type(type_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(PanelType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Panel type not found")
    section = db.get(EstimateSection, row.section_id)
    db.delete(row)
    db.flush()
    if section is not None:
        _recost(db, section)
    db.commit()
