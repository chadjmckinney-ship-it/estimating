"""
Rates on ONE section (sql/055) — read, resolved, and seeded.

Two things live here so the router and the seeding share one truth.

`rows(db, section)` is every rate key this section reads, with the whole
ladder behind each — section, job, assembly, company, code default — the same
resolution `calc._rate_numeric` performs, reported rather than recomputed by
the screen, so the two cannot disagree about what the section is paying.

`seed(db, section)` is Chad, 2026-09-05: **"Rates are always per section."**
Every section-level PRICE the section reads is written onto the section at
the value it resolves to right now, so from then on it is the section's own:
a later change to the job's price sheet or the company's settings moves
nothing that already exists, and two sections of one kind on one job share
nothing. Materials, equipment day rates and supervision day rates are the
job's (price_book.ESTIMATE_LEVEL_KEYS) and are never seeded; rules — waste,
divisors, how the work is computed — are read live by design and are never
seeded either. Idempotent: a key already set on the section is left alone.

Which keys? Not a hand-written list of "keys a paving section reads" — that
would drift from the line sets the day somebody adds a line. The takeoff is
RUN inside `recording_rates()` and the keys it actually asked for are the
keys, plus anything already set here and anything this assembly names in
`assembly_rates`. Nothing is stored by the read: it builds the line sets and
throws them away.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.estimate_section import EstimateSection
from app.schemas.section_rate import SectionRateRead
from app.services import price_book as pb
from app.services.calc import _setting_numeric


def known(key: str) -> bool:
    return key in pb.MONETARY_KEYS or key in pb.RULE_KEYS


def _d(x: Any) -> Decimal | None:
    return None if x is None else Decimal(str(x))


def keys_read(db: Session, section: EstimateSection) -> dict[str, Decimal]:
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


def rows(db: Session, section: EstimateSection) -> list[SectionRateRead]:
    kind = section.kind
    read = keys_read(db, section)

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
        if not known(key):
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


def seed(db: Session, section: EstimateSection, *, note: str | None = None) -> list[str]:
    """
    Make every section-level price this section reads the section's own, at
    the value it resolves to right now. Returns the keys written; a key
    already set here is left alone, so the call is safe to repeat. The note
    says when and from which rung — "seeded 2026-09-05 from the assembly" —
    so the rates card can show where the number was born.

    The caller commits. Nothing is recalculated: every value written is the
    value the section was already paying, so no stored number moves.
    """
    stamp = note or f"seeded {date.today().isoformat()}"
    written: list[str] = []
    for r in rows(db, section):
        if r.level != "section" or not r.is_price or not r.was_read:
            continue
        if r.source == "section" or r.value is None:
            continue
        db.execute(
            text(
                "INSERT INTO section_rates (section_id, key, value, note) "
                "VALUES (:s, :k, :v, :n) "
                "ON CONFLICT (section_id, key) DO NOTHING"
            ),
            {"s": str(section.id), "k": r.key, "v": r.value, "n": f"{stamp} from the {r.source}"},
        )
        written.append(r.key)
    return written
