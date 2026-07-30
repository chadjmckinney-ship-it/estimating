from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.grade_beam import GradeBeam
from app.models.mono_slab import MonoSlab
from app.schemas.grade_beam import (
    BEAM_KINDS,
    BeamKind,
    GradeBeamBulkReplace,
    GradeBeamCreate,
    GradeBeamRead,
    GradeBeamUpdate,
)
from app.services.calc import refresh_grade_beam_calcs, refresh_mono_slab_calcs

router = APIRouter(tags=["grade-beams"])

# Soft UI guidance — not a hard DB limit
MIN_GB_TYPES_UI = 5

KIND_LABELS = {
    "grade_beam": "grade beam",
    "exposed": "exposed GB",
    "drop": "drop",
}


def _to_read(row: GradeBeam) -> GradeBeamRead:
    return GradeBeamRead.model_validate(row)


def _resync_parent_slab(db: Session, mono_slab_id: UUID) -> None:
    slab = db.get(MonoSlab, mono_slab_id)
    if slab:
        refresh_mono_slab_calcs(db, slab)


def _resync_estimate_takeoffs(db: Session, mono_slab_id: UUID) -> None:
    """
    Refresh the estimate's stored forming/labor/equipment after a beam change.

    Beams feed all three: drop-kind length is the drops driver behind the 2x4,
    bracing and ply lines and the labor DROPS line (sql/022), beam rebar feeds
    forming accessories and labor tie steel, and beam concrete feeds equipment
    pumping. Without this a beam edit silently leaves those lines on the
    previous quantities.

    Call after commit — the pour calcs must already be written. Pours are not
    recalculated here; _resync_parent_slab has already done the one that moved.
    """
    from app.models.estimate import Estimate
    from app.services.recalc import recalc_estimate

    slab = db.get(MonoSlab, mono_slab_id)
    if slab is None:
        return
    estimate = db.get(Estimate, slab.estimate_id)
    if estimate is None:
        return
    recalc_estimate(db, estimate, pours=False)


def _validate_kind(kind: str) -> BeamKind:
    if kind not in BEAM_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {list(BEAM_KINDS)}",
        )
    return kind  # type: ignore[return-value]


@router.get("/grade-beams", response_model=list[GradeBeamRead])
def list_grade_beams(
    mono_slab_id: UUID = Query(...),
    kind: BeamKind | None = Query(
        None, description="Filter: grade_beam | exposed | drop. Omit for all."
    ),
    db: Session = Depends(get_db),
) -> list[GradeBeamRead]:
    stmt = select(GradeBeam).where(GradeBeam.mono_slab_id == mono_slab_id)
    if kind is not None:
        stmt = stmt.where(GradeBeam.kind == kind)
    stmt = stmt.order_by(GradeBeam.kind, GradeBeam.sort_order, GradeBeam.created_at)
    return [_to_read(r) for r in db.scalars(stmt).all()]


@router.get("/grade-beams/{beam_id}", response_model=GradeBeamRead)
def get_grade_beam(beam_id: UUID, db: Session = Depends(get_db)) -> GradeBeamRead:
    row = db.get(GradeBeam, beam_id)
    if not row:
        raise HTTPException(status_code=404, detail="Grade beam not found")
    return _to_read(row)


@router.post(
    "/grade-beams",
    response_model=GradeBeamRead,
    status_code=status.HTTP_201_CREATED,
)
def create_grade_beam(body: GradeBeamCreate, db: Session = Depends(get_db)) -> GradeBeamRead:
    if not db.get(MonoSlab, body.mono_slab_id):
        raise HTTPException(status_code=400, detail="mono_slab_id not found")
    _validate_kind(body.kind)
    data = body.model_dump()
    # PT cables only for grade beams poured with SOG
    if data.get("kind") != "grade_beam":
        data["pt_cables_count"] = None
    row = GradeBeam(**data)
    db.add(row)
    db.flush()
    refresh_grade_beam_calcs(db, row)
    db.flush()
    _resync_parent_slab(db, row.mono_slab_id)
    db.commit()
    _resync_estimate_takeoffs(db, row.mono_slab_id)
    db.refresh(row)
    return _to_read(row)


@router.patch("/grade-beams/{beam_id}", response_model=GradeBeamRead)
def update_grade_beam(
    beam_id: UUID, body: GradeBeamUpdate, db: Session = Depends(get_db)
) -> GradeBeamRead:
    row = db.get(GradeBeam, beam_id)
    if not row:
        raise HTTPException(status_code=404, detail="Grade beam not found")
    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] is not None:
        _validate_kind(data["kind"])
    for k, v in data.items():
        setattr(row, k, v)
    if row.kind != "grade_beam":
        row.pt_cables_count = None
    row.updated_at = datetime.now(timezone.utc)
    refresh_grade_beam_calcs(db, row)
    db.flush()
    _resync_parent_slab(db, row.mono_slab_id)
    db.commit()
    _resync_estimate_takeoffs(db, row.mono_slab_id)
    db.refresh(row)
    return _to_read(row)


@router.delete("/grade-beams/{beam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grade_beam(beam_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(GradeBeam, beam_id)
    if not row:
        raise HTTPException(status_code=404, detail="Grade beam not found")
    slab_id = row.mono_slab_id
    db.delete(row)
    db.flush()
    _resync_parent_slab(db, slab_id)
    db.commit()
    _resync_estimate_takeoffs(db, slab_id)


@router.put(
    "/mono-slabs/{slab_id}/grade-beams",
    response_model=list[GradeBeamRead],
)
def replace_grade_beams(
    slab_id: UUID,
    body: GradeBeamBulkReplace,
    db: Session = Depends(get_db),
) -> list[GradeBeamRead]:
    """
    Replace all beams of one kind on a mono slab pour.
    Does not touch other kinds (save GBs without wiping Exp/Drops).
    Incomplete rows (missing width/height or zero length) are skipped.
    """
    slab = db.get(MonoSlab, slab_id)
    if not slab:
        raise HTTPException(status_code=404, detail="Mono slab not found")

    kind = _validate_kind(body.kind)

    db.execute(
        delete(GradeBeam).where(
            GradeBeam.mono_slab_id == slab_id,
            GradeBeam.kind == kind,
        )
    )
    db.flush()

    created: list[GradeBeam] = []
    order = 0
    default_label = {
        "grade_beam": "GB Type",
        "exposed": "EXP Type",
        "drop": "Drop Type",
    }[kind]

    for item in body.beams:
        if item.length_lf is None or item.length_lf <= 0:
            continue
        if item.width_in is None or item.height_in is None:
            continue
        if item.width_in <= 0 or item.height_in <= 0:
            continue
        order += 10
        pt = item.pt_cables_count if kind == "grade_beam" else None
        row = GradeBeam(
            mono_slab_id=slab_id,
            kind=kind,
            label=item.label or f"{default_label} {order // 10}",
            width_in=item.width_in,
            height_in=item.height_in,
            length_lf=item.length_lf,
            top_bars_count=item.top_bars_count,
            top_bars_size=item.top_bars_size,
            bottom_bars_count=item.bottom_bars_count,
            bottom_bars_size=item.bottom_bars_size,
            mid_bars_count=item.mid_bars_count,
            mid_bars_size=item.mid_bars_size,
            stirrup_size=item.stirrup_size,
            stirrup_spacing_in=item.stirrup_spacing_in,
            l_bars_count=item.l_bars_count,
            l_bars_size=item.l_bars_size,
            l_bars_spacing_in=item.l_bars_spacing_in,
            pt_cables_count=pt,
            notes=item.notes,
            sort_order=item.sort_order if item.sort_order else order,
        )
        db.add(row)
        db.flush()
        refresh_grade_beam_calcs(db, row)
        created.append(row)

    db.flush()
    refresh_mono_slab_calcs(db, slab)
    db.commit()
    _resync_estimate_takeoffs(db, slab_id)
    for r in created:
        db.refresh(r)
    return [_to_read(r) for r in created]
