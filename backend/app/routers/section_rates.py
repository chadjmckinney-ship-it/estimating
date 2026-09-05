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

Since 2026-09-05 the read and the ladder live in services/section_rates.py,
because the seeding — "Rates are always per section" — needs the same truth
the screen shows. This module keeps the HTTP and the write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate_section import EstimateSection
from app.schemas.section_rate import (
    SectionRatesRead,
    SectionRateWrite,
)
from app.services import price_book as pb
from app.services import section_rates as sr

router = APIRouter(prefix="/sections", tags=["section-rates"])


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


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
    rows = sr.rows(db, section)
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
    if not sr.known(key):
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
