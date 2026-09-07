"""
Per-estimate grade beam / exposed GB / drop schedule (sql/025).

A type is defined once and referenced by every pour that uses it, so editing one
moves every pour it appears in — those recalcs happen here rather than being
left for the next page load.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.beam_type import EstimateBeamType
from app.models.estimate_section import EstimateSection
from app.models.grade_beam import GradeBeam
from app.schemas.beam_type import (
    BeamTypeBulk,
    BeamTypeBulkResult,
    BeamKind,
    BeamTypeCreate,
    BeamTypeRead,
    BeamTypeUpdate,
)

router = APIRouter(tags=["beam-types"])


def _usage(db: Session, type_id: UUID) -> dict[str, object]:
    """Where a type is used and what it contributes across the estimate."""
    row = db.execute(
        text(
            """
            SELECT count(*)::int              AS n,
                   coalesce(sum(length_lf), 0)        AS lf,
                   coalesce(sum(calc_concrete_cy), 0) AS cy,
                   coalesce(sum(calc_rebar_lb), 0)    AS rebar,
                   coalesce(sum(calc_poly_sf), 0)     AS poly,
                   coalesce(sum(calc_pt_cable_lf), 0) AS pt_lf
            FROM grade_beams WHERE beam_type_id = :t
            """
        ),
        {"t": str(type_id)},
    ).mappings().one()
    return {
        "pour_count": int(row["n"] or 0),
        "total_lf": Decimal(str(row["lf"] or 0)),
        "total_concrete_cy": Decimal(str(row["cy"] or 0)),
        "total_rebar_lb": Decimal(str(row["rebar"] or 0)),
        "total_poly_sf": Decimal(str(row["poly"] or 0)),
        "total_pt_cable_lf": Decimal(str(row["pt_lf"] or 0)),
    }


def _to_read(db: Session, row: EstimateBeamType) -> BeamTypeRead:
    used = _usage(db, row.id)
    return BeamTypeRead(
        id=row.id,
        section_id=row.section_id,
        label=row.label,
        kind=row.kind,
        width_in=row.width_in,
        height_in=row.height_in,
        form_face_in=row.form_face_in,
        top_bars_count=row.top_bars_count,
        top_bars_size=row.top_bars_size,
        bottom_bars_count=row.bottom_bars_count,
        bottom_bars_size=row.bottom_bars_size,
        mid_bars_count=row.mid_bars_count,
        mid_bars_size=row.mid_bars_size,
        stirrup_size=row.stirrup_size,
        stirrup_spacing_in=row.stirrup_spacing_in,
        l_bars_count=row.l_bars_count,
        l_bars_size=row.l_bars_size,
        l_bars_spacing_in=row.l_bars_spacing_in,
        pt_cables_count=row.pt_cables_count,
        notes=row.notes,
        sort_order=row.sort_order,
        **used,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _recalc_section(db: Session, section_id: UUID) -> None:
    """
    A type edit moves every pour using it, so redo the whole section — and do
    it BEFORE the commit. Until 2026-09-06 (audit P3) the routes below
    committed the type first and recalculated after, so a recalc that failed
    left the type changed and every pour stale, with the client shown an
    error for a write that had already happened. `recalc_section` does not
    commit; it ends in the pour costing that rolls the job up, and the caller
    commits once, when everything agrees.
    """
    from app.services.recalc import recalc_section

    section = db.get(EstimateSection, section_id)
    if section is None:
        return
    recalc_section(db, section)
    db.flush()


@router.get("/sections/{section_id}/beam-types", response_model=list[BeamTypeRead])
def list_beam_types(
    section_id: UUID,
    kind: BeamKind | None = Query(None, description="grade_beam | exposed | drop"),
    db: Session = Depends(get_db),
) -> list[BeamTypeRead]:
    if not db.get(EstimateSection, section_id):
        raise HTTPException(status_code=404, detail="Section not found")
    stmt = select(EstimateBeamType).where(EstimateBeamType.section_id == section_id)
    if kind is not None:
        stmt = stmt.where(EstimateBeamType.kind == kind)
    stmt = stmt.order_by(EstimateBeamType.sort_order, EstimateBeamType.label)
    return [_to_read(db, r) for r in db.scalars(stmt).all()]


@router.post(
    "/sections/{section_id}/beam-types",
    response_model=BeamTypeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_beam_type(
    section_id: UUID, body: BeamTypeCreate, db: Session = Depends(get_db)
) -> BeamTypeRead:
    if not db.get(EstimateSection, section_id):
        raise HTTPException(status_code=404, detail="Section not found")
    data = body.model_dump()
    data["label"] = data["label"].strip()
    # PT cables only apply to beams poured with the SOG.
    if data["kind"] != "grade_beam":
        data["pt_cables_count"] = None
    row = EstimateBeamType(section_id=section_id, **data)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"A type named '{body.label}' already exists"
        ) from None
    db.refresh(row)
    return _to_read(db, row)


@router.put("/sections/{section_id}/beam-types/bulk", response_model=BeamTypeBulkResult)
def save_beam_types(
    section_id: UUID, body: BeamTypeBulk, db: Session = Depends(get_db)
) -> BeamTypeBulkResult:
    """
    The grade-beams modal's "Save schedule": every row of the schedule in one
    request — one recalc of the section, one commit, and a bad row saves
    nothing. Until 2026-09-06 (audit P3) the modal PATCHed the types one at a
    time: five recalcs for five types, and a failure on the third left the
    first two saved and the rest not. A row with an id updates that type
    (only the fields sent); a row without one is created. Nothing is deleted
    here — that is the type editor's job, with its usage check.
    """
    if db.get(EstimateSection, section_id) is None:
        raise HTTPException(status_code=404, detail="Section not found")
    # Resolve every row before touching any: a stray id is refused with the
    # section exactly as it was.
    existing: dict[int, EstimateBeamType] = {}
    for i, r in enumerate(body.rows):
        if r.id is None:
            continue
        row = db.get(EstimateBeamType, r.id)
        if row is None or row.section_id != section_id:
            raise HTTPException(
                status_code=400, detail=f"rows.{i}: beam type {r.id} is not on this section"
            )
        existing[i] = row
    created = updated = 0
    for i, r in enumerate(body.rows):
        row = existing.get(i)
        data = r.model_dump(exclude={"id"}, exclude_unset=row is not None)
        if "label" in data:
            data["label"] = data["label"].strip()
        kind = data.get("kind") or (row.kind if row is not None else "grade_beam")
        if kind != "grade_beam":
            data["pt_cables_count"] = None  # PT cables only apply to beams poured with the SOG
        if row is None:
            db.add(EstimateBeamType(section_id=section_id, **data))
            created += 1
            continue
        for k, v in data.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
        updated += 1
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Two types on this section share a name") from None
    _recalc_section(db, section_id)
    db.commit()
    stmt = (
        select(EstimateBeamType)
        .where(EstimateBeamType.section_id == section_id)
        .order_by(EstimateBeamType.sort_order, EstimateBeamType.label)
    )
    return BeamTypeBulkResult(
        created=created, updated=updated, rows=[_to_read(db, x) for x in db.scalars(stmt).all()]
    )


@router.patch("/beam-types/{type_id}", response_model=BeamTypeRead)
def update_beam_type(
    type_id: UUID, body: BeamTypeUpdate, db: Session = Depends(get_db)
) -> BeamTypeRead:
    row = db.get(EstimateBeamType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Beam type not found")
    data = body.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        data["label"] = data["label"].strip()
    for k, v in data.items():
        setattr(row, k, v)
    if row.kind != "grade_beam":
        row.pt_cables_count = None
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A type with that name already exists") from None
    _recalc_section(db, row.section_id)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/beam-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_beam_type(
    type_id: UUID,
    force: bool = Query(
        False, description="Delete even though pours still use it (removes those too)"
    ),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(EstimateBeamType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Beam type not found")
    section_id = row.section_id
    used = _usage(db, type_id)
    pours, lf = used["pour_count"], used["total_lf"]
    if pours and not force:
        # Deleting cascades to the usages, so say what would be lost.
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{row.label}' is used by {pours} pour(s) totalling {lf} LF. "
                "Remove it from those pours first, or pass force=true."
            ),
        )
    db.delete(row)
    db.flush()
    _recalc_section(db, section_id)
    db.commit()


@router.get("/beam-types/{type_id}/usage", response_model=list[dict])
def beam_type_usage(type_id: UUID, db: Session = Depends(get_db)) -> list[dict]:
    """Which pours use this type, and for how much."""
    if not db.get(EstimateBeamType, type_id):
        raise HTTPException(status_code=404, detail="Beam type not found")
    rows = db.execute(
        text(
            """
            SELECT m.id::text AS mono_slab_id, m.description, gb.length_lf
            FROM grade_beams gb
            JOIN mono_slabs m ON m.id = gb.mono_slab_id
            WHERE gb.beam_type_id = :t
            ORDER BY m.sort_order, m.created_at
            """
        ),
        {"t": str(type_id)},
    ).mappings().all()
    return [dict(r) for r in rows]
