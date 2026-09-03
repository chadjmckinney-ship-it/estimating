from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.models.mix_design import MixDesign
from app.models.mono_slab import MonoSlab
from app.schemas.mono_slab import (
    MonoSlabBulkResult,
    MonoSlabBulkSave,
    MonoSlabCreate,
    MonoSlabRead,
    MonoSlabTotals,
    MonoSlabUpdate,
)
from app.services.calc import (
    _rate_numeric,
    beam_kind_breakdown,
    section_kind,
    section_mono_totals,
    refresh_mono_slab_calcs,
)
from app.services.pours import BulkSaveError, bulk_save_pours

router = APIRouter(prefix="/mono-slabs", tags=["mono-slabs"])


def _to_read(db: Session, row: MonoSlab) -> MonoSlabRead:
    mix = db.get(MixDesign, row.mix_design_id) if row.mix_design_id else None
    # The effective rates are what the calc actually used, so they resolve the
    # same way it does: this assembly first, then the company (sql/035–036).
    # Paving carries no support steel, and reading 0.1 here would have been a
    # number on screen that no quantity in the section agrees with.
    kind = section_kind(db, row.section_id)
    sys_support = _rate_numeric(db, kind, "support_rebar_lb_per_sf", Decimal("0.1"))
    sys_pt = _rate_numeric(db, kind, "pt_lb_per_sf", Decimal("1.0"))
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
        section_id=row.section_id,
        description=row.description,
        location=row.location,
        square_footage=row.square_footage,
        thickness_in=row.thickness_in,
        post_tension=row.post_tension,
        mix_design_id=row.mix_design_id,
        sand_thickness_in=row.sand_thickness_in,
        perimeter_edge_lf=row.perimeter_edge_lf,
        wire_mesh=row.wire_mesh,
        slab_bar_size=row.slab_bar_size,
        slab_bar_spacing_in=row.slab_bar_spacing_in,
        support_rebar_lb_per_sf=row.support_rebar_lb_per_sf,
        pt_lb_per_sf=row.pt_lb_per_sf,
        pt_spacing_in=row.pt_spacing_in,
        curb_lf=row.curb_lf,
        thick_edge_lf=row.thick_edge_lf,
        demo_lf=row.demo_lf,
        slip_form=row.slip_form,
        traffic_control=row.traffic_control,
        paving_add_per_sf=row.paving_add_per_sf,
        mesh_gauge=row.mesh_gauge,
        notes=row.notes,
        sort_order=row.sort_order,
        calc_concrete_cy=row.calc_concrete_cy,
        calc_slab_concrete_cy=row.calc_slab_concrete_cy,
        calc_gb_concrete_cy=row.calc_gb_concrete_cy,
        calc_edge_concrete_cy=row.calc_edge_concrete_cy,
        calc_sand_cy=row.calc_sand_cy,
        calc_slab_bar_lf=row.calc_slab_bar_lf,
        calc_slab_bar_lb=row.calc_slab_bar_lb,
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
        calc_sf_per_cy=row.calc_sf_per_cy,
        calc_direct_cost=row.calc_direct_cost,
        calc_allocated_cost=row.calc_allocated_cost,
        calc_equip_fuel=row.calc_equip_fuel,
        calc_tax=row.calc_tax,
        calc_cost=row.calc_cost,
        calc_sale=row.calc_sale,
        calc_cost_per_sf=row.calc_cost_per_sf,
        calc_sale_per_sf=row.calc_sale_per_sf,
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


def _recost(db: Session, section: EstimateSection) -> None:
    """
    Re-run the WHOLE section — geometry, forming, labor, equipment, cost.

    All four write paths below used to call `refresh_pour_costs` alone, which
    reprices the pours and leaves the three stored takeoffs on their pre-edit
    quantities. Only `/bulk` ran `recalc_section`, so typing a pour's SF into
    the grid was correct and editing that same pour through its own row was not.

    This is also where paving lives, and paving forms off CURB LF: changing a
    row's curb moved the concrete and left every lumber line in the package
    behind it. A mono-slab PATCH was measured $1,278,678.90 adrift on the job
    total before `_roll_up_parent` and this landed together.
    """
    from app.services.recalc import recalc_section

    recalc_section(db, section)


@router.get("", response_model=list[MonoSlabRead])
def list_mono_slabs(
    section_id: UUID = Query(..., description="Parent section"),
    db: Session = Depends(get_db),
) -> list[MonoSlabRead]:
    stmt = (
        select(MonoSlab)
        .where(MonoSlab.section_id == section_id)
        .order_by(MonoSlab.sort_order, MonoSlab.created_at)
    )
    return [_to_read(db, r) for r in db.scalars(stmt).all()]


@router.get("/totals", response_model=MonoSlabTotals)
def mono_slab_totals(
    section_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> MonoSlabTotals:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    t = section_mono_totals(db, section_id)
    # Named on purpose (sql/030): which roll this section is wrapped in, and
    # whether anyone chose it. A "fallback" here is a name search nobody
    # looked at — the screen says so beside the picker (audit #8).
    from app.services.costing import resolve_rebar, resolve_vapor_barrier, resolve_vapor_tape, vapor_barrier_source

    t["vapor_barrier"] = (resolve_vapor_barrier(db, section) or {}).get("name")
    t["vapor_barrier_source"] = vapor_barrier_source(section, db)
    t["vapor_tape"] = (resolve_vapor_tape(db, section) or {}).get("name")
    return MonoSlabTotals(section_id=section_id, **t)


@router.get("/{slab_id}", response_model=MonoSlabRead)
def get_mono_slab(slab_id: UUID, db: Session = Depends(get_db)) -> MonoSlabRead:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    return _to_read(db, row)


@router.post("", response_model=MonoSlabRead, status_code=status.HTTP_201_CREATED)
def create_mono_slab(body: MonoSlabCreate, db: Session = Depends(get_db)) -> MonoSlabRead:
    section = db.get(EstimateSection, body.section_id)
    if not section:
        raise HTTPException(status_code=400, detail="section_id not found")
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    row = MonoSlab(
        section_id=body.section_id,
        description=body.description,
        location=body.location,
        square_footage=body.square_footage,
        thickness_in=body.thickness_in,
        post_tension=body.post_tension,
        mix_design_id=body.mix_design_id,
        sand_thickness_in=body.sand_thickness_in,
        perimeter_edge_lf=body.perimeter_edge_lf,
        wire_mesh=body.wire_mesh,
        slab_bar_size=body.slab_bar_size,
        slab_bar_spacing_in=body.slab_bar_spacing_in,
        support_rebar_lb_per_sf=body.support_rebar_lb_per_sf,
        pt_lb_per_sf=body.pt_lb_per_sf,
        pt_spacing_in=body.pt_spacing_in,
        curb_lf=body.curb_lf,
        thick_edge_lf=body.thick_edge_lf,
        demo_lf=body.demo_lf,
        slip_form=body.slip_form,
        traffic_control=body.traffic_control,
        paving_add_per_sf=body.paving_add_per_sf,
        mesh_gauge=body.mesh_gauge,
        notes=body.notes,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.flush()  # get id for grade beam query
    refresh_mono_slab_calcs(db, row, section)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.put("/bulk", response_model=MonoSlabBulkResult)
def bulk_save_mono_slabs(
    body: MonoSlabBulkSave, db: Session = Depends(get_db)
) -> MonoSlabBulkResult:
    """
    Save a whole grid of pours in one request.

    Paving is entered as a table, and a field-at-a-time save would re-run the
    section's forming, labor and equipment on every keystroke — all three key
    off the section totals, so every one of them changes when any row does.
    Here the rows are written first and the section is recalculated once.

    Rows the grid did not send are left alone unless delete_missing is set. A
    save that quietly deletes work the user could not see is a worse failure
    than a row that has to be deleted twice.
    """
    section = db.get(EstimateSection, body.section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    payload = [
        {**r.model_dump(exclude_unset=True, exclude={"id"}), **({"id": r.id} if r.id else {})}
        for r in body.rows
    ]
    try:
        counts = bulk_save_pours(
            db, section, payload, delete_missing=body.delete_missing
        )
    except BulkSaveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = [
        _to_read(db, r)
        for r in db.scalars(
            select(MonoSlab)
            .where(MonoSlab.section_id == body.section_id)
            .order_by(MonoSlab.sort_order, MonoSlab.created_at)
        ).all()
    ]
    return MonoSlabBulkResult(
        section_id=body.section_id,
        created=counts["created"],
        updated=counts["updated"],
        deleted=counts["deleted"],
        rows=rows,
        totals=MonoSlabTotals(
            section_id=body.section_id, **section_mono_totals(db, body.section_id)
        ),
    )


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
    section = db.get(EstimateSection, row.section_id)
    refresh_mono_slab_calcs(db, row, section)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.post("/{slab_id}/recalc", response_model=MonoSlabRead)
def recalc_mono_slab(slab_id: UUID, db: Session = Depends(get_db)) -> MonoSlabRead:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    section = db.get(EstimateSection, row.section_id)
    refresh_mono_slab_calcs(db, row, section)
    row.updated_at = datetime.now(timezone.utc)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/{slab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mono_slab(slab_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(MonoSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mono slab not found")
    sid = row.section_id
    db.delete(row)
    db.flush()

    section = db.get(EstimateSection, sid)
    if section is not None:
        _recost(db, section)
    db.commit()
