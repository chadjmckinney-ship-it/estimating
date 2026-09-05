"""
Sections — the assemblies of a job (sql/033–034).

A job used to *be* a mono-slab worksheet. It is now a list of sections, each
one an assembly with its own rates, takeoff, markup and (optionally) its own tax
treatment, mirroring the per-sheet level of the workbook this replaces.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.estimate_section import (
    DEFAULT_UNIT_BY_KIND,
    PIER_KINDS,
    SECTION_KINDS,
    EstimateSection,
)
from app.models.project import Project
from app.services.calc import _rate_numeric, _waste
from app.schemas.estimate_section import (
    EstimateSectionCreate,
    EstimateSectionRead,
    EstimateSectionUpdate,
)
from app.schemas.material_costs import SectionMaterialCosts

router = APIRouter(tags=["estimate-sections"])


def _effective_exempt(db: Session, row: EstimateSection) -> bool | None:
    """What tax treatment actually applied — the section's, else the project's."""
    if row.tax_exempt is not None:
        return row.tax_exempt
    est = db.get(Estimate, row.estimate_id)
    if est is None:
        return None
    project = db.get(Project, est.project_id)
    return bool(getattr(project, "tax_exempt", False)) if project else None


def _effective_waste(db: Session, row: EstimateSection, field: str) -> Decimal:
    """
    The waste factor this section's quantities were actually computed with.

    Since sql/036 "not set here" no longer means "the company number": paving
    wastes concrete at 6% and steel at 10% because the paving sheet does, and
    the screen said "sys" for all three. A factor the estimator cannot read is
    a factor they cannot question.
    """
    return _waste(row, db, field, field)


def _d(x) -> Decimal:
    return Decimal(str(x)) if x is not None and x != "" else Decimal("0")


def _quote_state(db: Session, row: EstimateSection) -> dict:
    """
    The quotes on this section, each with what it replaced and whether it can
    still be trusted (sql/039).

    `quote_kinds` is what this assembly *can* carry, so the screen knows which
    cards to draw without hard-coding the mapping in two languages.
    """
    from app.services import quotes as qt

    kinds = qt.kinds_for(getattr(row, "kind", None))
    loaded = qt.load_quotes(db, row.id)
    out = []
    for k in kinds:
        q = loaded.get(k)
        if q is None:
            continue
        current = qt.section_driver_qty(db, row, k)
        out.append(
            {
                "kind": k,
                "label": qt.QUOTE_KINDS[k]["label"],
                "amount": q.amount,
                "unit": q.unit,
                "note": q.note,
                "baseline_qty": q.baseline_qty,
                "baseline_unit": qt.QUOTE_KINDS[k]["driver"],
                "current_qty": current,
                # Only a lump can drift — a unit price follows the takeoff.
                "stale": qt.is_stale(q, current),
                # Quote against catalog. Always present; only the verdict is
                # conditional (sql/046).
                **qt.compare_to_catalog(db, row, q, current),
            }
        )
    return {"quote_kinds": kinds, "quotes": out}


def _to_read(db: Session, row: EstimateSection) -> EstimateSectionRead:
    return EstimateSectionRead(
        **_quote_state(db, row),
        effective_waste_concrete=_effective_waste(db, row, "waste_concrete"),
        effective_waste_sand=_effective_waste(db, row, "waste_sand"),
        effective_waste_rebar=_effective_waste(db, row, "waste_rebar"),
        effective_form_percent=(
            row.form_percent
            if row.form_percent is not None
            else _rate_numeric(db, row.kind, "form_percent", Decimal("0.50"))
        ),
        id=row.id,
        estimate_id=row.estimate_id,
        kind=row.kind,
        name=row.name,
        unit=row.unit,
        sort_order=row.sort_order,
        margin_pct=row.margin_pct,
        contingency_pct=row.contingency_pct,
        tax_exempt=row.tax_exempt,
        labor_subcontracted=bool(getattr(row, "labor_subcontracted", False)),
        effective_tax_exempt=_effective_exempt(db, row),
        form_percent=row.form_percent,
        waste_concrete=row.waste_concrete,
        waste_sand=row.waste_sand,
        waste_rebar=row.waste_rebar,
        vapor_barrier_material_id=row.vapor_barrier_material_id,
        vapor_tape_material_id=row.vapor_tape_material_id,
        footing_mix_design_id=row.footing_mix_design_id,
        notes=row.notes,
        calc_total_cost=row.calc_total_cost,
        calc_total_tax=row.calc_total_tax,
        calc_total_sale=row.calc_total_sale,
        calc_quantity=row.calc_quantity,
        calc_cost_per_unit=row.calc_cost_per_unit,
        calc_sale_per_unit=row.calc_sale_per_unit,
        # The read model is built field by field (a lesson from 2026-08-30), so
        # a new calc column has to be named here or it never reaches the screen.
        calc_unpriced=list(row.calc_unpriced or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/sections/meta/kinds", response_model=list[str])
def list_kinds() -> list[str]:
    return list(SECTION_KINDS)


@router.get("/estimates/{estimate_id}/sections", response_model=list[EstimateSectionRead])
def list_sections(
    estimate_id: UUID,
    db: Session = Depends(get_db),
) -> list[EstimateSectionRead]:
    if not db.get(Estimate, estimate_id):
        raise HTTPException(status_code=404, detail="Estimate not found")
    stmt = (
        select(EstimateSection)
        .where(EstimateSection.estimate_id == estimate_id)
        .order_by(EstimateSection.sort_order, EstimateSection.created_at)
    )
    return [_to_read(db, r) for r in db.scalars(stmt).all()]


@router.post(
    "/estimates/{estimate_id}/sections",
    response_model=EstimateSectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_section(
    estimate_id: UUID, body: EstimateSectionCreate, db: Session = Depends(get_db)
) -> EstimateSectionRead:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if body.kind not in SECTION_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown section kind: {body.kind}")

    data = body.model_dump(exclude_unset=True)
    # A new section starts at the job's markup defaults unless it says otherwise.
    if data.get("margin_pct") is None:
        data["margin_pct"] = estimate.margin_pct or Decimal("0.20")
    if data.get("contingency_pct") is None:
        data["contingency_pct"] = estimate.contingency_pct or Decimal("0.00")
    if not data.get("unit"):
        data["unit"] = DEFAULT_UNIT_BY_KIND.get(body.kind, "SF")

    row = EstimateSection(estimate_id=estimate_id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    # Rates are always per section (Chad, 2026-09-05). A new section takes
    # every section-level price it reads at today's resolved value and owns
    # it from here — services/section_rates.seed. The job's sheet and the
    # company's settings are where a NEW section starts, not what an existing
    # one follows.
    from app.services import section_rates as sr

    sr.seed(db, row)
    db.commit()
    return _to_read(db, row)


@router.get("/sections/{section_id}", response_model=EstimateSectionRead)
def get_section(section_id: UUID, db: Session = Depends(get_db)) -> EstimateSectionRead:
    row = db.get(EstimateSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    return _to_read(db, row)


@router.get(
    "/sections/{section_id}/material-costs", response_model=SectionMaterialCosts
)
def section_material_costs_endpoint(
    section_id: UUID, db: Session = Depends(get_db)
) -> SectionMaterialCosts:
    """
    The dollars behind the quantity cards — concrete, steel, poly, drilling.

    One endpoint for every assembly rather than three more fields on three
    totals schemas: the shape of the answer is the same everywhere (a list of
    purchases), only the list differs, and a section that grows a new material
    then needs no schema change to show it.
    """
    from app.services.material_costs import section_material_costs

    row = db.get(EstimateSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    return SectionMaterialCosts(**section_material_costs(db, row))


# Inputs that change what a section costs. Editing one has to rewrite the stored
# numbers, or the screen shows new factors over old results.
_POUR_FIELDS = frozenset({"waste_concrete", "waste_sand", "waste_rebar"})
# Fields that change the LABOR lines without changing a quantity. Subbing the
# labor moves no money (sql/052) — it moves which bucket every field line is
# in, and the lines are stored, so they have to be rewritten or the screen
# keeps showing the old answer.
_LABOR_FIELDS = frozenset({"labor_subcontracted"})
_COSTING_FIELDS = frozenset(
    {"vapor_barrier_material_id", "vapor_tape_material_id", "margin_pct",
     "contingency_pct", "tax_exempt", "footing_mix_design_id"}
)


@router.patch("/sections/{section_id}", response_model=EstimateSectionRead)
def update_section(
    section_id: UUID, body: EstimateSectionUpdate, db: Session = Depends(get_db)
) -> EstimateSectionRead:
    row = db.get(EstimateSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] not in SECTION_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown section kind: {data['kind']}")

    changed = {k for k, v in data.items() if getattr(row, k) != v}
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)

    db.flush()

    from app.services.costing import refresh_estimate_totals, refresh_pour_costs
    from app.services.recalc import recalc_section

    if changed & _POUR_FIELDS:
        # A quantity moved: rebar feeds forming accessories and labor tie steel,
        # concrete CY feeds equipment pumping.
        recalc_section(db, row)
    elif "form_percent" in changed:
        recalc_section(db, row, pours=False, labor=False, equipment=False)
    elif changed & _LABOR_FIELDS:
        recalc_section(db, row, pours=False)
    elif changed & _COSTING_FIELDS:
        # A price or a rate changed, not a quantity — re-cost, don't re-take-off.
        refresh_pour_costs(db, row)

    if changed:
        estimate = db.get(Estimate, row.estimate_id)
        if estimate is not None:
            refresh_estimate_totals(db, estimate)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.post("/sections/{section_id}/recalc", response_model=EstimateSectionRead)
def recalc_section_endpoint(
    section_id: UUID, db: Session = Depends(get_db)
) -> EstimateSectionRead:
    from app.services.costing import refresh_estimate_totals
    from app.services.recalc import recalc_section

    row = db.get(EstimateSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    recalc_section(db, row)
    estimate = db.get(Estimate, row.estimate_id)
    if estimate is not None:
        refresh_estimate_totals(db, estimate)
    db.commit()
    db.refresh(row)
    return _to_read(db, row)


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(
    section_id: UUID,
    force: bool = Query(False, description="Delete even when the section has pours"),
    db: Session = Depends(get_db),
) -> None:
    from app.models.mono_slab import MonoSlab
    from app.services.costing import refresh_estimate_totals

    row = db.get(EstimateSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")

    pours = db.scalar(
        select(MonoSlab).where(MonoSlab.section_id == section_id).limit(1)
    )
    if pours is not None and not force:
        raise HTTPException(
            status_code=409,
            detail="Section still has pours. Re-send with force=true to delete them too.",
        )

    estimate_id = row.estimate_id
    db.delete(row)
    db.flush()
    estimate = db.get(Estimate, estimate_id)
    if estimate is not None:
        refresh_estimate_totals(db, estimate)
    db.commit()
