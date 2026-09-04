"""
Rules set on ONE job (sql/055's second table, given a screen).

`estimate_rules` has existed and resolved correctly since sql/055; setting one
still took SQL. This is the screen.

## Why rules are not on the price sheet

The split is the spine of the pricing design and this endpoint exists because
of it:

    a PRICE is frozen on the estimate's price sheet at its pull, so a company
    change leaves live bids alone;

    a RULE is read LIVE, so a correction to how the work is COMPUTED reaches
    the jobs it was made for.

Freezing a rule would break the second half. So a job that needs its own waste
factor, its own supervision pacing or its own divisor needs somewhere that is
not the sheet, and this is it.

## The ladder, from here down

    section_rates      this section (sql/055)          <- beats everything
      estimate_rules   THIS JOB — what this endpoint writes
        assembly_rates what a paving section does
          system_settings  what S&S does
            code default

with one thing above all of it for four keys: waste concrete/sand/rebar and
form % are COLUMNS on `estimate_sections`, checked in `calc._waste` before the
ladder runs at all. A job rule for those reaches only the sections that left
the column blank — which the row says out loud rather than quietly failing.

## Which keys are listed

Chad, asked: **"only what this job's sections read."** So the same mechanism
the section card uses — each section's takeoff is RUN inside
`recording_rates()` and the union of what they asked for is the list. A
hand-written list would drift from the line sets the day somebody adds a line,
and a list of all 55 rules would mostly be rules that do nothing on this job.

**`read_by` is a positive signal, not a complete one.** Only three passes are
replayable without storing — forming, labor and equipment — so the GEOMETRY
pass is not recorded, and the rules it reads (`waste_concrete`, `pt_lb_per_sf`,
`support_rebar_lb_per_sf`, the rebar wastes) come back with an empty
`read_by` even though the deck plainly reads them. They are still listed,
because `assembly_rates` names them, and the screen deliberately does NOT say
"nothing reads this" — an empty `read_by` means "not observed", and printing it
as "not used" would be a false statement about the one rule an estimator most
wants to set per job.

Nothing is stored by the GET. It builds the line sets and throws them away.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.routers.system_settings import _group_for
from app.schemas.estimate_rule import (
    EstimateRuleRead,
    EstimateRulesRead,
    EstimateRuleWrite,
    RuleSectionUse,
)
from app.services import price_book as pb
from app.services.calc import _setting_numeric

router = APIRouter(prefix="/estimates", tags=["estimate-rules"])

# The four rules that are also COLUMNS on estimate_sections, checked by
# `calc._waste` before `_rate_numeric` is called at all. Named here so the
# screen can say "this section answers it itself" instead of showing a job
# number that section never sees.
SECTION_COLUMN_KEYS: dict[str, str] = {
    "waste_concrete": "waste_concrete",
    "waste_sand": "waste_sand",
    "waste_rebar": "waste_rebar",
    "form_percent": "form_percent",
}


def _estimate_or_404(db: Session, estimate_id: UUID) -> Estimate:
    row = db.get(Estimate, estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return row


def _d(x: Any) -> Decimal | None:
    return None if x is None else Decimal(str(x))


def _label_for(key: str) -> str:
    """
    A rule has no entry in MONETARY_KEYS — that registry is prices, with their
    units. So the label is the key made readable, and the real explanation is
    `system_settings.description`, which sql/054 exists to keep filled in.
    Inventing a second label registry here would be a second thing to keep in
    step with the first.
    """
    return key.replace("_", " ").strip().capitalize()


def _sections(db: Session, estimate_id: UUID) -> list[EstimateSection]:
    return list(
        db.scalars(
            select(EstimateSection)
            .where(EstimateSection.estimate_id == estimate_id)
            .order_by(EstimateSection.sort_order, EstimateSection.created_at)
        ).all()
    )


def _keys_each_section_reads(
    db: Session, sections: list[EstimateSection]
) -> dict[UUID, dict[str, Decimal | None]]:
    """
    Per section, the rate keys its takeoff actually asked for.

    Same three calc functions the section card runs, for the same reason: the
    list cannot drift from the line sets because it IS the line sets. A section
    that cannot build (no rows yet, half-entered) contributes nothing rather
    than taking the job's screen down with it.
    """
    from app.services.estimate_equipment import calc_estimate_equipment
    from app.services.forming import calc_forming_materials
    from app.services.labor import calc_labor_materials

    out: dict[UUID, dict[str, Decimal | None]] = {}
    for section in sections:
        with pb.recording_rates() as seen:
            for fn in (
                calc_forming_materials,
                calc_labor_materials,
                calc_estimate_equipment,
            ):
                try:
                    fn(db, section.id)
                except Exception:  # noqa: BLE001
                    continue
        out[section.id] = seen
    return out


def _rows(db: Session, estimate: Estimate) -> list[EstimateRuleRead]:
    sections = _sections(db, estimate.id)
    read = _keys_each_section_reads(db, sections)

    job = {
        r[0]: (Decimal(str(r[1])), r[2])
        for r in db.execute(
            text("SELECT key, value, note FROM estimate_rules WHERE estimate_id = :e"),
            {"e": str(estimate.id)},
        ).all()
    }

    kinds = {s.kind for s in sections}
    assembly: dict[str, dict[str, Decimal]] = {}
    if kinds:
        for r in db.execute(
            text("SELECT kind, key, value FROM assembly_rates WHERE kind = ANY(:ks)"),
            {"ks": list(kinds)},
        ).all():
            assembly.setdefault(r[1], {})[r[0]] = Decimal(str(r[2]))

    # Every section's own overrides, so the card can say which sections are not
    # listening. One query rather than one per row.
    per_section: dict[str, dict[UUID, Decimal]] = {}
    for r in db.execute(
        text(
            "SELECT sr.key, sr.section_id, sr.value FROM section_rates sr "
            "JOIN estimate_sections es ON es.id = sr.section_id "
            "WHERE es.estimate_id = :e"
        ),
        {"e": str(estimate.id)},
    ).all():
        per_section.setdefault(r[0], {})[r[1]] = Decimal(str(r[2]))

    by_id = {s.id: s for s in sections}
    descriptions = {
        r[0]: r[1]
        for r in db.execute(
            text("SELECT key, description FROM system_settings")
        ).all()
    }

    keys = {k for seen in read.values() for k in seen} | set(job) | set(assembly)
    out: list[EstimateRuleRead] = []
    for key in sorted(keys):
        # PRICES are not editable here on purpose — they are frozen on the
        # price sheet, which is its own screen and already edits them per job.
        # A key on neither registry has no defensible behaviour anywhere;
        # test_price_sheet_rates fails the day one appears.
        if key not in pb.RULE_KEYS:
            continue

        company = _setting_numeric(db, key, Decimal("NaN"))
        company_val = None if company.is_nan() else company
        job_val, note = job.get(key, (None, None))
        asm = assembly.get(key, {})
        # A default the takeoff reported. Sections agree on these (they are
        # literals in the code), so the first one that answered is the answer.
        default = next(
            (seen[key] for seen in read.values() if seen.get(key) is not None), None
        )

        if job_val is not None:
            value, source = job_val, "job"
        elif len(set(asm.values())) == 1:
            # One assembly answer across every kind on this job, so it IS the
            # job's answer. Two different ones is not a number this row can
            # honestly print, and falls through to what the company says.
            value, source = next(iter(asm.values())), "assembly"
        elif company_val is not None:
            value, source = company_val, "company"
        else:
            value, source = default, "default"

        # Which sections do NOT end up using the job's answer. The column wins
        # over the section rate, because `calc._waste` checks it before the
        # ladder runs — reporting them the other way round would name the wrong
        # number as the one in force.
        col = SECTION_COLUMN_KEYS.get(key)
        mine = per_section.get(key, {})
        overridden: list[RuleSectionUse] = []
        for section in sections:
            column = _d(getattr(section, col, None)) if col else None
            own = mine.get(section.id)
            if column is not None:
                answer, why = column, "column"
            elif own is not None:
                answer, why = own, "section"
            else:
                continue
            overridden.append(
                RuleSectionUse(
                    section_id=section.id,
                    name=section.name,
                    kind=section.kind,
                    value=answer,
                    source=why,
                )
            )

        group, group_order = _group_for(key)
        out.append(
            EstimateRuleRead(
                key=key,
                label=_label_for(key),
                description=descriptions.get(key),
                group=group,
                group_order=group_order,
                value=value,
                source=source,
                job_value=job_val,
                note=note,
                assembly_values=asm,
                company_value=company_val,
                default_value=default,
                is_section_column=col is not None,
                read_by=[
                    by_id[sid].name for sid in read if key in read[sid] and sid in by_id
                ],
                overridden_by=overridden,
            )
        )
    return out


def _recost(db: Session, estimate: Estimate) -> None:
    """
    A rule change rewrites the WHOLE JOB.

    A rule is read live, which is exactly why it cannot be left to a later
    recalc: the stored `calc_*` columns every screen and every total reads were
    computed under the OLD rule, and until something rewrites them the job
    shows one number while the rule says another. sql/053 shipped a company
    key that rewrote nothing and reported success — the same failure, one
    layer up.
    """
    from app.services.recalc import recalc_estimate

    recalc_estimate(db, estimate)


@router.get("/{estimate_id}/rules", response_model=EstimateRulesRead)
def get_estimate_rules(
    estimate_id: UUID, db: Session = Depends(get_db)
) -> EstimateRulesRead:
    estimate = _estimate_or_404(db, estimate_id)
    rows = _rows(db, estimate)
    return EstimateRulesRead(
        estimate_id=estimate.id,
        name=estimate.name,
        rows=rows,
        set_here=sum(1 for r in rows if r.job_value is not None),
        section_count=len(_sections(db, estimate.id)),
    )


@router.put("/{estimate_id}/rules/{key}", response_model=EstimateRulesRead)
def set_estimate_rule(
    estimate_id: UUID,
    key: str,
    body: EstimateRuleWrite,
    db: Session = Depends(get_db),
) -> EstimateRulesRead:
    estimate = _estimate_or_404(db, estimate_id)
    if key in pb.MONETARY_KEYS:
        # Refused loudly and with somewhere to go, rather than accepted and
        # quietly ignored: `_rate_numeric` never consults estimate_rules for a
        # monetary key, so a row written here would sit in the table looking
        # like a decision and change nothing at all. That is worse than no box.
        label = pb.MONETARY_KEYS[key][0]
        raise HTTPException(
            status_code=400,
            detail=(
                f"{label} is a PRICE, and this job's prices are frozen on its "
                "price sheet — set it there so it stays put for the life of "
                "the bid. Rules are read live; prices are not."
            ),
        )
    if key not in pb.RULE_KEYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{key}' is not a rule this app reads. Keys come from "
                "price_book.RULE_KEYS."
            ),
        )
    db.execute(
        text(
            "INSERT INTO estimate_rules (estimate_id, key, value, note) "
            "VALUES (:e, :k, :v, :n) "
            "ON CONFLICT (estimate_id, key) DO UPDATE "
            "SET value = excluded.value, note = excluded.note, updated_at = :t"
        ),
        {
            "e": str(estimate_id), "k": key, "v": body.value, "n": body.note,
            "t": datetime.now(timezone.utc),
        },
    )
    db.flush()
    _recost(db, estimate)
    return get_estimate_rules(estimate_id, db)


@router.delete("/{estimate_id}/rules/{key}", response_model=EstimateRulesRead)
def clear_estimate_rule(
    estimate_id: UUID, key: str, db: Session = Depends(get_db)
) -> EstimateRulesRead:
    """
    Remove the job rule, so the assembly and the company decide again.

    Deleting rather than blanking, for the reason sql/055 already wrote down:
    there is no "unset" row. A row means somebody decided; no row means nobody
    did, and a zero is a decision somebody makes on purpose.
    """
    estimate = _estimate_or_404(db, estimate_id)
    db.execute(
        text("DELETE FROM estimate_rules WHERE estimate_id = :e AND key = :k"),
        {"e": str(estimate_id), "k": key},
    )
    db.flush()
    _recost(db, estimate)
    return get_estimate_rules(estimate_id, db)
