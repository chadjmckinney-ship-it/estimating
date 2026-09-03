"""
A pour's use of the estimate's beam types: which type, and how many LF.

The section and bar schedule live on estimate_beam_types (sql/025); these rows
carry only the quantity.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.beam_type import EstimateBeamType
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
    """Flatten the usage with its type so a UI row needs no second lookup."""
    t = row.beam_type
    return GradeBeamRead(
        id=row.id,
        mono_slab_id=row.mono_slab_id,
        beam_type_id=row.beam_type_id,
        length_lf=row.length_lf,
        notes=row.notes,
        sort_order=row.sort_order,
        label=t.label if t else None,
        kind=t.kind if t else "grade_beam",
        width_in=t.width_in if t else None,
        height_in=t.height_in if t else None,
        top_bars_count=t.top_bars_count if t else None,
        top_bars_size=t.top_bars_size if t else None,
        bottom_bars_count=t.bottom_bars_count if t else None,
        bottom_bars_size=t.bottom_bars_size if t else None,
        mid_bars_count=t.mid_bars_count if t else None,
        mid_bars_size=t.mid_bars_size if t else None,
        stirrup_size=t.stirrup_size if t else None,
        stirrup_spacing_in=t.stirrup_spacing_in if t else None,
        l_bars_count=t.l_bars_count if t else None,
        l_bars_size=t.l_bars_size if t else None,
        l_bars_spacing_in=t.l_bars_spacing_in if t else None,
        pt_cables_count=t.pt_cables_count if t else None,
        calc_rebar_lb=row.calc_rebar_lb,
        calc_pt_cable_lf=row.calc_pt_cable_lf,
        calc_concrete_cy=row.calc_concrete_cy,
        calc_poly_sf=row.calc_poly_sf,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _resync_parent_slab(db: Session, mono_slab_id: UUID) -> None:
    slab = db.get(MonoSlab, mono_slab_id)
    if slab:
        refresh_mono_slab_calcs(db, slab)


def _resync_section_takeoffs(db: Session, mono_slab_id: UUID) -> None:
    """
    Refresh the section's stored forming/labor/equipment after a beam change,
    then roll the job up. Flushes; does NOT commit — the caller owns that.

    Beams feed all three: drop-kind length is the drops driver behind the 2x4,
    bracing and ply lines and the labor DROPS line (sql/022), beam rebar feeds
    forming accessories and labor tie steel, and beam concrete feeds equipment
    pumping. Without this a beam edit silently leaves those lines on the
    previous quantities.

    Pours are not recalculated here; _resync_parent_slab has already done the
    one that moved.

    ## Two things changed here on 2026-09-02, both of them bugs

    This function used to read `slab.estimate_id` and hand the whole ESTIMATE to
    `recalc_estimate`. Neither half survived sql/034, which moved pours and beam
    types under a section:

      * `MonoSlab.estimate_id` has not existed since that migration, so this
        raised `AttributeError` and every grade-beam write returned 500. It ran
        AFTER `db.commit()`, so the beam was written, the client got an error,
        and the takeoffs never resynced — the worst of the three possible
        orderings. No test covered these routes, so 346 of them passed over it.
      * Even fixed in place it was the wrong SCOPE. A beam belongs to one pour,
        which belongs to one section; repricing every other section of the job
        because a drop moved is work nobody asked for, and on a five-section job
        it is most of a recalc.

    So: recalc the SECTION, then roll the estimate up — the section total is not
    the job total, and `refresh_pour_costs` only writes the former.
    """
    from app.models.estimate_section import EstimateSection
    from app.services.recalc import recalc_section

    slab = db.get(MonoSlab, mono_slab_id)
    if slab is None:
        return
    section = db.get(EstimateSection, slab.section_id)
    if section is None:
        return
    # The job roll-up rides along: `recalc_section` ends in `refresh_pour_costs`,
    # which is the only writer of a section total and now re-adds the job from
    # its sections there. This function rolled the estimate up explicitly for a
    # few hours on 2026-09-02, before that became structural — see
    # `costing._roll_up_parent`.
    recalc_section(db, section, pours=False)
    db.flush()


def _type_for_slab(db: Session, slab: MonoSlab, beam_type_id: UUID) -> EstimateBeamType:
    """A pour may only use types belonging to its own SECTION (sql/034)."""
    t = db.get(EstimateBeamType, beam_type_id)
    if t is None:
        raise HTTPException(status_code=400, detail="beam_type_id not found")
    if t.section_id != slab.section_id:
        raise HTTPException(
            status_code=400,
            detail="beam_type_id belongs to a different section",
        )
    return t


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
    stmt = (
        select(GradeBeam)
        .join(EstimateBeamType, EstimateBeamType.id == GradeBeam.beam_type_id)
        .where(GradeBeam.mono_slab_id == mono_slab_id)
    )
    if kind is not None:
        stmt = stmt.where(EstimateBeamType.kind == kind)
    stmt = stmt.order_by(
        EstimateBeamType.kind, GradeBeam.sort_order, EstimateBeamType.label
    )
    return [_to_read(r) for r in db.scalars(stmt).unique().all()]


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
    slab = db.get(MonoSlab, body.mono_slab_id)
    if not slab:
        raise HTTPException(status_code=400, detail="mono_slab_id not found")
    _type_for_slab(db, slab, body.beam_type_id)
    row = GradeBeam(
        mono_slab_id=body.mono_slab_id,
        beam_type_id=body.beam_type_id,
        length_lf=body.length_lf,
        notes=body.notes,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.flush()
    refresh_grade_beam_calcs(db, row)
    db.flush()
    _resync_parent_slab(db, row.mono_slab_id)
    # Resync BEFORE the commit, so the beam and the takeoffs it moves land in
    # one transaction. The old order committed first and resynced after, which
    # is how a 500 left a written beam beside stale forming and labor.
    _resync_section_takeoffs(db, row.mono_slab_id)
    db.commit()
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
    if data.get("beam_type_id") is not None:
        slab = db.get(MonoSlab, row.mono_slab_id)
        _type_for_slab(db, slab, data["beam_type_id"])
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    refresh_grade_beam_calcs(db, row)
    db.flush()
    _resync_parent_slab(db, row.mono_slab_id)
    _resync_section_takeoffs(db, row.mono_slab_id)
    db.commit()
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
    _resync_section_takeoffs(db, slab_id)
    db.commit()


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
    Replace this pour's usages for one kind. Other kinds are untouched, so
    saving GBs will not wipe Exp or Drops.

    Rows with length <= 0 are dropped — clearing a length removes that type from
    the pour.
    """
    slab = db.get(MonoSlab, slab_id)
    if not slab:
        raise HTTPException(status_code=404, detail="Mono slab not found")

    kind = _validate_kind(body.kind)

    # Validate every referenced type before deleting anything.
    wanted: list[tuple[UUID, GradeBeamBulkReplace]] = []
    for item in body.beams:
        if item.length_lf is None or item.length_lf <= 0:
            continue
        t = _type_for_slab(db, slab, item.beam_type_id)
        if t.kind != kind:
            raise HTTPException(
                status_code=400,
                detail=f"'{t.label}' is a {KIND_LABELS[t.kind]}, not a {KIND_LABELS[kind]}",
            )
        wanted.append((t, item))

    existing_ids = [
        r.id
        for r in db.scalars(
            select(GradeBeam)
            .join(EstimateBeamType, EstimateBeamType.id == GradeBeam.beam_type_id)
            .where(GradeBeam.mono_slab_id == slab_id, EstimateBeamType.kind == kind)
        ).unique().all()
    ]
    if existing_ids:
        db.execute(delete(GradeBeam).where(GradeBeam.id.in_(existing_ids)))
        db.flush()

    created: list[GradeBeam] = []
    order = 0
    for t, item in wanted:
        order += 10
        row = GradeBeam(
            mono_slab_id=slab_id,
            beam_type_id=t.id,
            length_lf=item.length_lf,
            notes=item.notes,
            sort_order=item.sort_order or order,
        )
        db.add(row)
        db.flush()
        refresh_grade_beam_calcs(db, row)
        created.append(row)

    db.flush()
    refresh_mono_slab_calcs(db, slab)
    _resync_section_takeoffs(db, slab_id)
    db.commit()
    for r in created:
        db.refresh(r)
    return [_to_read(r) for r in created]
