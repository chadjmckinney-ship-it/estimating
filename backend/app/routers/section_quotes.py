"""
Quotes on a section (sql/039).

    GET    /api/sections/{id}/quotes            what is quoted, and what it replaced
    PUT    /api/sections/{id}/quotes/{kind}     write one (amount 0 clears it)
    DELETE /api/sections/{id}/quotes/{kind}     clear one

A write stamps the baseline for a lump and re-costs the section. Both matter:
the baseline is what makes the staleness warning possible at all, and without
the re-cost the screen would show a new quote over old money.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.models.section_quote import SectionQuote
from app.schemas.section_quote import SectionQuoteRead, SectionQuoteWrite
from app.services import quotes as qt

router = APIRouter(prefix="/api/sections", tags=["section-quotes"])


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    row = db.get(EstimateSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    return row


def _read(db: Session, section: EstimateSection, row: SectionQuote) -> SectionQuoteRead:
    spec = qt.QUOTE_KINDS[row.kind]
    current = qt.section_driver_qty(db, section, row.kind)
    q = qt.QuoteSet([row]).get(row.kind)
    cmp = qt.compare_to_catalog(db, section, q, current)
    return SectionQuoteRead(
        **cmp,
        kind=row.kind,
        label=spec["label"],
        amount=row.amount,
        unit=row.unit,
        note=row.note,
        baseline_qty=row.baseline_qty,
        baseline_unit=spec["driver"],
        current_qty=current,
        stale=qt.is_stale(q, current),
    )


def _recost(db: Session, section: EstimateSection) -> None:
    """
    Rewrite the stored money under this section, and roll the job up.

    A drilling quote also has to re-run the pier groups first, because it is
    spread onto `calc_drill_cost` before costing ever reads it. Rebar and PT
    quotes are consumed by costing directly, so they need no takeoff pass —
    and deliberately do not get one: re-running the takeoff would discard any
    manual line the estimator has pinned.
    """
    from app.models.estimate_section import PIER_KINDS
    from app.services.costing import refresh_estimate_totals, refresh_pour_costs

    if section.kind in PIER_KINDS:
        from app.services.piers import refresh_section_pier_calcs

        refresh_section_pier_calcs(db, section)
        db.flush()

    refresh_pour_costs(db, section)
    estimate = db.get(Estimate, section.estimate_id)
    if estimate is not None:
        refresh_estimate_totals(db, estimate)


@router.get("/{section_id}/quotes", response_model=list[SectionQuoteRead])
def list_quotes(section_id: UUID, db: Session = Depends(get_db)) -> list[SectionQuoteRead]:
    section = _section_or_404(db, section_id)
    rows = db.scalars(
        select(SectionQuote).where(SectionQuote.section_id == section_id)
    ).all()
    return [_read(db, section, r) for r in rows]


@router.put("/{section_id}/quotes/{kind}", response_model=list[SectionQuoteRead])
def put_quote(
    section_id: UUID,
    kind: str,
    body: SectionQuoteWrite,
    db: Session = Depends(get_db),
) -> list[SectionQuoteRead]:
    section = _section_or_404(db, section_id)

    if kind not in qt.QUOTE_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown quote kind: {kind}")
    allowed = qt.kinds_for(section.kind)
    if kind not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A {section.kind} section cannot carry a {kind} quote. "
                f"It accepts: {', '.join(allowed) or 'none'}"
            ),
        )
    units = qt.units_for(kind)
    if body.unit not in units:
        raise HTTPException(
            status_code=400,
            detail=f"A {kind} quote is priced in {' or '.join(units)}, not {body.unit}",
        )

    existing = db.scalar(
        select(SectionQuote).where(
            SectionQuote.section_id == section_id, SectionQuote.kind == kind
        )
    )

    # 0 clears rather than pricing the package at nothing.
    if body.amount <= 0:
        if existing is not None:
            db.delete(existing)
            db.flush()
            _recost(db, section)
        db.commit()
        return list_quotes(section_id, db)

    spec = qt.QUOTE_KINDS[kind]
    is_lump = body.unit == "LS"
    # Stamped on write and nowhere else. A unit price gets no baseline because
    # it cannot drift — it follows the takeoff by construction — and stamping
    # one anyway would invite a staleness check that fires on a quote that is
    # perfectly current.
    baseline = qt.section_driver_qty(db, section, kind) if is_lump else None

    if existing is None:
        existing = SectionQuote(section_id=section_id, kind=kind)
        db.add(existing)
    existing.amount = body.amount
    existing.unit = body.unit
    existing.note = body.note
    existing.baseline_qty = baseline
    existing.baseline_unit = spec["driver"] if is_lump else None
    existing.updated_at = datetime.now(timezone.utc)
    db.flush()

    _recost(db, section)
    db.commit()
    return list_quotes(section_id, db)


@router.delete("/{section_id}/quotes/{kind}", response_model=list[SectionQuoteRead])
def delete_quote(
    section_id: UUID, kind: str, db: Session = Depends(get_db)
) -> list[SectionQuoteRead]:
    section = _section_or_404(db, section_id)
    row = db.scalar(
        select(SectionQuote).where(
            SectionQuote.section_id == section_id, SectionQuote.kind == kind
        )
    )
    if row is not None:
        db.delete(row)
        db.flush()
        _recost(db, section)
    db.commit()
    return list_quotes(section_id, db)
