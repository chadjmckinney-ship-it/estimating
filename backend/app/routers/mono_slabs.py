from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.mix_design import MixDesign
from app.models.mono_slab import MonoSlab
from app.schemas.mono_slab import (
    MonoSlabCreate,
    MonoSlabRead,
    MonoSlabTotals,
    MonoSlabUpdate,
)
from app.services.calc import (
    _setting_numeric,
    beam_kind_breakdown,
    estimate_mono_totals,
    refresh_mono_slab_calcs,
)

router = APIRouter(prefix="/mono-slabs", tags=["mono-slabs"])


def _to_read(db: Session, row: MonoSlab) -> MonoSlabRead:
    mix = db.get(MixDesign, row.mix_design_id) if row.mix_design_id else None
    sys_support = _setting_numeric(db, "support_rebar_lb_per_sf", Decimal("1.0"))
    sys_pt = _setting_numeric(db, "pt_lb_per_sf", Decimal("1.0"))
    eff_support = (
        Decimal(str(row.support_rebar_lb_per_sf))
        if row.support_rebar_lb_per_sf is not None
        else sys_support
    )
    eff_pt = (
        Decimal(str(row.pt_lb_per_sf)) if row.pt_lb_per_sf is not None else sys_pt
    )
    breakdown = beam_kind_breakdown(db, row.id)
    return MonoSlabRead(
        id=row.id,
        estimate_id=row.estimate_id,
        description=row.description,
        location=row.location,
        square_footage=row.square_footage,
        thickness_in=row.thickness_in,
        post_tension=row.post_tension,
        mix_design_id=row.mix_design_id,
        sand_thickness_in=row.sand_thickness_in,
        perimeter_edge_lf=row.perimeter_edge_lf,
        wire_mesh=row.wire_mesh,
        drops_ff=row.drops_ff,
        support_rebar_lb_per_sf=row.support_rebar_lb_per_sf,
        pt_lb_per_sf=row.pt_lb_per_sf,
        pt_spacing_in=row.pt_spacing_in,
        notes=row.notes,
        sort_order=row.sort_order,
        calc_concrete_cy=row.calc_concrete_cy,
        calc_slab_concrete_cy=row.calc_slab_concrete_cy,
        calc_gb_concrete_cy=row.calc_gb_concrete_cy,
        calc_sand_cy=row.calc_sand_cy,
        calc_support_rebar_lb=row.calc_support_rebar_lb,
        calc_pt_cable_lb=row.calc_pt_cable_lb,
        calc_pt_slab_lf=row.calc_pt_slab_lf,
        calc_pt_gb_lf=row.calc_pt_gb_lf,
        calc_pt_cable_lf=row.calc_pt_cable_lf,
        calc_grade_beam_rebar_lb=row.calc_grade_beam_rebar_lb,
        calc_total_rebar_lb=row.calc_total_rebar_lb,
        calc_poly_slab_sf=row.calc_poly_slab_sf,
        calc_poly_gb_sf=row.calc_poly_gb_sf,
        calc_poly_sf=row.calc_poly_sf,
        beam_breakdown=breakdown,
        effective_support_rebar_lb_per_sf=eff_support,
        effective_pt_lb_per_sf=eff_pt,
        mix_design_name=mix.name if mix else None,
        mix_design_code=mix.code if mix else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _optional_num(v):
    if v is None or v == "":
        return None
    return v


@router.get("", response_model=list[MonoSlabRead])
def list_mono_slabs(
    estimate_id: UUID = Query(..., description="Parent estimate"),
    db: Session = Depends(get_db),
) -> list[MonoSlabRead]:
    stmt = (
        select(MonoSlab)
        .where(MonoSlab.estimate_id == estimate_id)
        .order_by(MonoSlab.sort_order, MonoSlab.created_at)
    )
    return [_to_read(db, r) for r in db.scalars(stmt).all()]


@router.get("/totals", response_model=MonoSlabTotals)
def mono_slab_totals(
    estimate_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> MonoSlabTotals:
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    t = estimate_mono_totals(db, estimate_id)
    return MonoSlabTotals(estimate_id=estimate_id, **t)


@router.get("/{slab_id}", response_model=MonoSlabRead)
def get_mono_slab(slab_id: UUID, db: Session = Depends(get_db)) -> MonoSlabRead:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    return _to_read(db, row)


@router.post("", response_model=MonoSlabRead, status_code=status.HTTP_201_CREATED)
def create_mono_slab(body: MonoSlabCreate, db: Session = Depends(get_db)) -> MonoSlabRead:
    estimate = db.get(Estimate, body.estimate_id)
    if not estimate:
        raise HTTPException(status_code=400, detail="estimate_id not found")
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    row = MonoSlab(
        estimate_id=body.estimate_id,
        description=body.description,
        location=body.location,
        square_footage=body.square_footage,
        thickness_in=body.thickness_in,
        post_tension=body.post_tension,
        mix_design_id=body.mix_design_id,
        sand_thickness_in=body.sand_thickness_in,
        perimeter_edge_lf=body.perimeter_edge_lf,
        wire_mesh=body.wire_mesh,
        drops_ff=body.drops_ff,
        support_rebar_lb_per_sf=body.support_rebar_lb_per_sf,
        pt_lb_per_sf=body.pt_lb_per_sf,
        pt_spacing_in=body.pt_spacing_in,
        notes=body.notes,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.flush()  # get id for grade beam query
    refresh_mono_slab_calcs(db, row, estimate)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.patch("/{slab_id}", response_model=MonoSlabRead)
def update_mono_slab(
    slab_id: UUID, body: MonoSlabUpdate, db: Session = Depends(get_db)
) -> MonoSlabRead:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    data = body.model_dump(exclude_unset=True)
    if "mix_design_id" in data and data["mix_design_id"] is not None:
        if not db.get(MixDesign, data["mix_design_id"]):
            raise HTTPException(status_code=400, detail="mix_design_id not found")
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    estimate = db.get(Estimate, row.estimate_id)
    refresh_mono_slab_calcs(db, row, estimate)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.post("/{slab_id}/recalc", response_model=MonoSlabRead)
def recalc_mono_slab(slab_id: UUID, db: Session = Depends(get_db)) -> MonoSlabRead:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    estimate = db.get(Estimate, row.estimate_id)
    refresh_mono_slab_calcs(db, row, estimate)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/{slab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mono_slab(slab_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    db.delete(row)
    db.commit()
