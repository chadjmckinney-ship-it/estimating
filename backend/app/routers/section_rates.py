"""
Rates set on ONE section (sql/055).

Chad, 2026-09-04, asked for the company settings to be editable per estimate —
"lets say a place and finish sub says for a project, he can do it for less
because of the size of the pours" — and then, asked where the override should
live: **"I think making rates changes per section is what I would like the
best."**

Which is the right instinct: what makes the sub cheaper is the size of THESE
pours, not the job. A job with two paving sections could not say that before
this, because the price sheet is per estimate.

## What this endpoint is really for

Not the editing — that is two lines. It is **saying where each number came
from**. Every row reports the whole ladder:

    section    this section's own override        (sql/055)
    job        the estimate's price sheet, or its rule override
    assembly   what a paving section does
    company    what S&S does
    default    the literal in the code, when nothing else answered

A rate you cannot trace is a rate you cannot defend three months later, and
this app has spent its whole life finding numbers nobody could explain.

## Which keys are listed

Not a hand-written list of "keys a paving section reads" — that would drift
from the line sets the day somebody adds a line. The takeoff is RUN inside
`recording_rates()` and the keys it actually asked for are the keys shown,
plus anything already overridden here and anything this assembly names in
`assembly_rates`.

Nothing is stored by the GET. It builds the line sets and throws them away.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import EstimateSection
from app.schemas.section_rate import (
    SectionRateRead,
    SectionRatesRead,
    SectionRateWrite,
)
from app.services import price_book as pb
from app.services.calc import _setting_numeric

router = APIRouter(prefix="/sections", tags=["section-rates"])


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


def _known(key: str) -> bool:
    return key in pb.MONETARY_KEYS or key in pb.RULE_KEYS


def _d(x: Any) -> Decimal | None:
    return None if x is None else Decimal(str(x))


def _keys_this_section_reads(db: Session, section: EstimateSection) -> dict[str, Decimal]:
    """
    Every rate key this section's takeoff actually READ, and the code default
    behind each.

    Built by running the three line sets inside `recording_rates()` rather than
    from a list. A list would be six lists, one per assembly, and they would
    disagree with the line sets within a month — the same argument that put the
    price/rule split in one registry instead of in the front end.

    Nothing is stored: these are the calc functions, not the refresh-and-store
    ones.
    """
    from app.services.estimate_equipment import calc_estimate_equipment
    from app.services.forming import calc_forming_materials
    from app.services.labor import calc_labor_materials

    with pb.recording_rates() as seen:
        for fn in (calc_forming_materials, calc_labor_materials, calc_estimate_equipment):
            try:
                fn(db, section.id)
            except Exception:  # noqa: BLE001
                # A takeoff that cannot build (no rows yet, a half-entered
                # section) must not take the rates screen down with it. The
                # keys the other two read still list.
                continue
    return seen


def _rows(db: Session, section: EstimateSection) -> list[SectionRateRead]:
    kind = section.kind
    read = _keys_this_section_reads(db, section)

    overrides = {
        r[0]: (Decimal(str(r[1])), r[2])
        for r in db.execute(
            text("SELECT key, value, note FROM section_rates WHERE section_id = :s"),
            {"s": str(section.id)},
        ).all()
    }
    assembly = {
        r[0]: Decimal(str(r[1]))
        for r in db.execute(
            text("SELECT key, value FROM assembly_rates WHERE kind = :k"), {"k": kind}
        ).all()
    }
    job_rules = {
        r[0]: Decimal(str(r[1]))
        for r in db.execute(
            text("SELECT key, value FROM estimate_rules WHERE estimate_id = :e"),
            {"e": str(section.estimate_id)},
        ).all()
    }

    book = pb.load_price_book(db, section.estimate_id)

    keys = set(read) | set(overrides) | set(assembly) | set(job_rules)
    out: list[SectionRateRead] = []
    for key in sorted(keys):
        if not _known(key):
            # A key in neither registry has no defensible behaviour here —
            # nothing decides whether it freezes. test_price_sheet_rates fails
            # the day one appears; this just declines to invent a row for it.
            continue
        is_price = key in pb.MONETARY_KEYS
        level = pb.rate_level(key)
        label, unit = pb.MONETARY_KEYS.get(key, (key, None))
        company = _setting_numeric(db, key, Decimal("NaN"))
        company_val = None if company.is_nan() else company
        job = (
            (book.rate(kind, key) if book.has_sheet else None)
            if is_price
            else job_rules.get(key)
        )
        default = read.get(key)

        # The ladder, resolved here the same way calc._rate_numeric resolves
        # it. Reported rather than recomputed by the screen, so the two cannot
        # disagree about what this section is actually paying.
        section_val = overrides.get(key, (None, None))[0]
        if section_val is not None:
            value, source = section_val, "section"
        elif job is not None:
            value, source = job, "job"
        elif is_price and book.has_sheet:
            # "Once a sheet exists it is the only source" — a price missing
            # from the sheet lands on the code default, NOT on the tables.
            value, source = default, "default"
        elif key in assembly:
            value, source = assembly[key], "assembly"
        elif company_val is not None:
            value, source = company_val, "company"
        else:
            value, source = default, "default"

        out.append(
            SectionRateRead(
                key=key,
                label=label,
                unit=unit,
                is_price=is_price,
                level=level,
                value=value,
                source=source,
                section_value=section_val,
                note=overrides.get(key, (None, None))[1],
                job_value=job,
                assembly_value=assembly.get(key),
                company_value=company_val,
                default_value=default,
                was_read=key in read,
            )
        )
    return out


def _recost(db: Session, section: EstimateSection) -> None:
    """
    A rate change rewrites the WHOLE section.

    The same rule every write path in this app has learned the hard way: a
    rate feeds the takeoffs, the takeoffs feed the cost, and a per-row refresh
    leaves the rest stale. The columns router paid $436,826.42 to learn it.
    """
    from app.services.recalc import recalc_section

    recalc_section(db, section)


@router.get("/{section_id}/rates", response_model=SectionRatesRead)
def get_section_rates(
    section_id: UUID, db: Session = Depends(get_db)
) -> SectionRatesRead:
    section = _section_or_404(db, section_id)
    rows = _rows(db, section)
    return SectionRatesRead(
        section_id=section.id,
        estimate_id=section.estimate_id,
        kind=section.kind,
        name=section.name,
        rows=rows,
        overridden=sum(1 for r in rows if r.source == "section"),
    )


@router.put("/{section_id}/rates/{key}", response_model=SectionRatesRead)
def set_section_rate(
    section_id: UUID,
    key: str,
    body: SectionRateWrite,
    db: Session = Depends(get_db),
) -> SectionRatesRead:
    section = _section_or_404(db, section_id)
    if not _known(key):
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{key}' is not a rate this app reads. Keys come from "
                "price_book.MONETARY_KEYS or RULE_KEYS."
            ),
        )
    if pb.rate_level(key) != "section":
        # Chad's policy, 2026-09-04: labor is a section fact, material is a job
        # fact. "materials should be standard across the estimate. concrete and
        # materials are quoted per job so should be edited that way."
        #
        # Refused loudly and with somewhere to go, rather than accepted and
        # quietly ignored: a section paying a different price for PT cable than
        # the job that quoted it is a wrong number, and a wrong number with a
        # box that accepted it is worse than one with no box at all.
        label = pb.MONETARY_KEYS.get(key, (key, None))[0]
        raise HTTPException(
            status_code=400,
            detail=(
                f"{label} is set for the whole job, not per section — it is a "
                "material or a job fact, and the sub who quoted it quoted the "
                "job. Set it on the estimate's price sheet."
            ),
        )
    db.execute(
        text(
            "INSERT INTO section_rates (section_id, key, value, note) "
            "VALUES (:s, :k, :v, :n) "
            "ON CONFLICT (section_id, key) DO UPDATE "
            "SET value = excluded.value, note = excluded.note, updated_at = :t"
        ),
        {
            "s": str(section_id), "k": key, "v": body.value, "n": body.note,
            "t": datetime.now(timezone.utc),
        },
    )
    db.flush()
    _recost(db, section)
    db.commit()
    return get_section_rates(section_id, db)


@router.delete("/{section_id}/rates/{key}", response_model=SectionRatesRead)
def clear_section_rate(
    section_id: UUID, key: str, db: Session = Depends(get_db)
) -> SectionRatesRead:
    """
    Remove the override, so the ladder below takes over again.

    Deleting rather than blanking, on purpose: there is no "unset" row in
    `section_rates`. A row means somebody decided; no row means nobody did.
    """
    section = _section_or_404(db, section_id)
    db.execute(
        text("DELETE FROM section_rates WHERE section_id = :s AND key = :k"),
        {"s": str(section_id), "k": key},
    )
    db.flush()
    _recost(db, section)
    db.commit()
    return get_section_rates(section_id, db)
