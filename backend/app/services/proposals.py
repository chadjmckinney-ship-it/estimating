"""
The proposal (sql/080): seeding it from the estimate, refreshing it, reading
it whole, and naming its file.

A proposal is the estimate pushed onto the bid form. One proposal section per
estimate section, in order; one line per costed takeoff row — a pour, a pier
group, a wall run, a column type, a deck level, a beam run, a panel type, a
misc item — carrying the row's name, its quantity in the section's unit, its
sale per unit and its sale. Every line remembers the row it came from, so a
refresh can pull fresh quantities and prices onto it and leave the rewritten
description alone; a line typed by hand (haul-off, certified payroll,
pumping) has no source and is never touched by a refresh.

The takeoff is untouched by any of this. An excluded line is a proposal
status with its quantity kept; the row behind it still prices, and the
tie-out beside each section says so.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.beam_run import BeamRun
from app.models.column_type import ColumnType
from app.models.deck_level import DeckLevel
from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.models.misc_item import MiscItem
from app.models.mono_slab import MonoSlab
from app.models.panel_type import PanelType
from app.models.pier_group import PierGroup
from app.models.project import Project
from app.models.proposal import (
    BLOCKS,
    DISCIPLINES,
    Proposal,
    ProposalItem,
    ProposalLibraryItem,
    ProposalLine,
    ProposalSection,
)
from app.models.wall_run import WallRun

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")

INTRO_DEFAULT = (
    "We are pleased to submit a proposal for labor, material, and equipment as "
    "detailed herein to construct the items below."
)
PAYMENT_DEFAULT = "PER CONTRACT AGREEMENT OR UPON COMPLETION"

# The eight takeoff shapes a line can point back at.
MODEL_BY_TABLE = {
    MonoSlab.__tablename__: MonoSlab,
    PierGroup.__tablename__: PierGroup,
    WallRun.__tablename__: WallRun,
    ColumnType.__tablename__: ColumnType,
    DeckLevel.__tablename__: DeckLevel,
    BeamRun.__tablename__: BeamRun,
    PanelType.__tablename__: PanelType,
    MiscItem.__tablename__: MiscItem,
}


def _d(x: Any) -> Decimal:
    return Decimal(str(x)) if x is not None else Decimal("0")


def row_label(row: Any) -> str:
    """What a takeoff row calls itself: its label, else its description, else its code."""
    for attr in ("label", "description", "name", "code"):
        v = getattr(row, attr, None)
        if v:
            return str(v).strip()
    return "Item"


# ------------------------------------------------------- descriptions ----
#
# A seeded line starts with what the row IS, in the form's own idiom —
# "Building A (4" PT SOG 3000 PSI w/ Ash)", "G: 24" dia x 30' deep w/ 6-#6
# vert" — so the estimator rewrites a description rather than typing one
# from nothing. The library's standard (plan mark, item, location, thickness,
# psi, reinforcing, finish, the governing detail) is the target; this is the
# start. Every piece is optional and a missing one is simply left out.


def _n(x: Any) -> str:
    """A number the way the form writes it: 4, 4.5, 12, no trailing zeros."""
    if x is None:
        return ""
    d = Decimal(str(x)).normalize()
    return f"{d:f}" if d != d.to_integral_value() else str(int(d))


def _mix_name(db: Session, mix_id: Any) -> str | None:
    if not mix_id:
        return None
    from app.models.mix_design import MixDesign

    mix = db.get(MixDesign, mix_id)
    return (mix.name or mix.code) if mix is not None else None


def _bar(size: Any, spacing: Any, tail: str = " OCEW") -> str | None:
    if not size or not spacing:
        return None
    return f'#{int(size)} @ {_n(spacing)}"{tail}'


def _join(*parts: str | None, sep: str = " ") -> str:
    return sep.join(p for p in parts if p)


def _name(row: Any, fallback: str) -> str:
    label = (getattr(row, "label", None) or "").strip()
    desc = (getattr(row, "description", None) or "").strip()
    if label and desc:
        return f"{label} — {desc}"
    return label or desc or fallback


def describe_footing(db: Session, row: Any, section: EstimateSection, fallback: str = "Footing") -> str:
    """The footing under a wall run as its own line: `W1 footing: 70" x 12" footing, w/ #4 @ 12" OCEW bot, 4000 PSI`."""
    name = _name(row, fallback)
    mix = _mix_name(db, row.footing_mix_for(section))
    what = f'{_n(row.ftg_width_in)}" x {_n(row.ftg_thick_in)}" footing'
    bot = _bar(row.ftg_bot_size, row.ftg_bot_spacing_in, tail=" OCEW bot") if getattr(row, "ftg_bot_size", None) else None
    top = _bar(row.ftg_top_size, row.ftg_top_spacing_in, tail=" OCEW top") if getattr(row, "ftg_top_size", None) else None
    bars = _join(bot, top, sep=" / ")
    return f"{name} footing: {_join(what, f'w/ {bars}' if bars else None, mix, sep=', ')}"


def describe_row(db: Session, row: Any, kind: str | None, fallback: str = "Item") -> str:
    """The seeded description for a takeoff row: its name, then what it is in parentheses."""
    from app.models.estimate_section import CONT_KINDS, PAVING_KINDS, SIDEWALK_KINDS, SPOT_KINDS

    table = getattr(row, "__tablename__", "")
    mix = _mix_name(db, getattr(row, "mix_design_id", None))

    if table == "mono_slabs":
        name = (getattr(row, "description", None) or "").strip() or fallback
        thk = _n(row.thickness_in)
        if kind in PAVING_KINDS or kind in SIDEWALK_KINDS:
            what = f'{thk}" thick'
        else:
            what = f'{thk}" {"PT SOG" if row.post_tension else "SOG"}'
        mat = _bar(row.slab_bar_size, row.slab_bar_spacing_in)
        mesh = "w/ wire mesh" if getattr(row, "wire_mesh", False) else None
        inner = _join(what, mix, f"w/ {mat}" if mat else None, mesh)
        return f"{name} ({inner})"

    if table == "pier_groups":
        name = _name(row, fallback)
        depth = _n(row.base_depth_ft)
        rock = _n(row.rock_penetration_ft) if _d(row.rock_penetration_ft) > 0 else ""
        what = f'{_n(row.diameter_in)}" dia x {depth}\' deep' + (f" + {rock}' rock" if rock else "")
        bell = f'{_n(row.bell_size_in)}" bell' if getattr(row, "bell_size_in", None) else None
        vert = (
            f"w/ {row.vert_bars_count}-#{row.vert_bars_size} vert"
            if row.vert_bars_count and row.vert_bars_size
            else None
        )
        ties = _bar(row.tie_size, row.tie_spacing_in, tail=" ties") if row.tie_size else None
        return f"{name}: {_join(what, bell, mix, vert, ties, sep=', ')}"

    if table == "wall_runs":
        name = _name(row, fallback)
        if kind in SPOT_KINDS or getattr(row, "footing_each_ft", None) is not None:
            w_ft = _n(_d(row.ftg_width_in) / Decimal("12")) if row.ftg_width_in is not None else ""
            what = f"{_n(row.footing_each_ft)}' x {w_ft}' x {_n(row.ftg_thick_in)}\" footing"
            mat = _bar(row.ftg_bot_size, row.ftg_bot_spacing_in, tail=" OCEW bot") if getattr(row, "ftg_bot_size", None) else None
            plate = "weld plate" if getattr(row, "weld_plate", False) else None
            return f"{name}: {_join(what, mix, f'w/ {mat}' if mat else None, plate, sep=', ')}"
        # The wall alone: its footing is a line of its own (sql/081).
        wall = (
            f'{_n(row.wall_height_in)}" tall x {_n(row.wall_thick_in)}" wall'
            if row.wall_height_in is not None and row.wall_thick_in is not None
            else None
        )
        return f"{name}: {_join(wall, mix, sep=', ')}"

    if table == "column_types":
        name = _name(row, fallback)
        what = f'{_n(row.length_in)}" x {_n(row.width_in)}" x {_n(row.height_ft)}\' column'
        ties = _bar(row.tie_size, row.tie_spacing_in, tail=" ties") if row.tie_size else None
        return f"{name}: {_join(what, mix, ties, sep=', ')}"

    if table == "deck_levels":
        name = _name(row, fallback)
        what = f'{_n(row.thickness_in)}" {"PT " if getattr(row, "has_cable", False) else ""}slab on deck'
        top = _bar(row.top_bar_size, row.top_bar_spacing_in, tail=" top") if row.top_bar_size else None
        bot = _bar(row.bot_bar_size, row.bot_bar_spacing_in, tail=" bot") if row.bot_bar_size else None
        bars = _join(top, bot, sep=" / ")
        return f"{name}: {_join(what, mix, f'w/ {bars}' if bars else None, sep=', ')}"

    if table == "beam_runs":
        name = _name(row, fallback)
        noun = "continuous footing" if kind in CONT_KINDS else "grade beam"
        what = f'{_n(row.width_in)}" x {_n(row.height_in)}" {noun}'
        top = f"{row.top_bars_count}-#{row.top_bars_size} top" if row.top_bars_count and row.top_bars_size else None
        bot = (
            f"{row.bottom_bars_count}-#{row.bottom_bars_size} bot"
            if row.bottom_bars_count and row.bottom_bars_size
            else None
        )
        stir = _bar(row.stirrup_size, row.stirrup_spacing_in, tail=" stirrups") if row.stirrup_size else None
        bars = _join(top, bot, sep=" / ")
        return f"{name}: {_join(what, mix, f'w/ {bars}' if bars else None, stir, sep=', ')}"

    if table == "panel_types":
        name = _name(row, fallback)
        height = _d(row.top_el_ft) - _d(row.bot_el_ft)
        what = f"{_n(row.length_ft)}' x {_n(height)}' x {_n(row.thickness_in)}\" panel"
        return f"{name}: {_join(what, mix, sep=', ')}"

    if table == "misc_items":
        name = (getattr(row, "description", None) or "").strip() or fallback
        a, b, c = row.dim_a, row.dim_b, row.dim_c
        shape = getattr(row, "shape", None)
        dims = None
        if shape == "round" and a is not None and b is not None:
            dims = f'{_n(a)}" dia x {_n(b)}\' deep'
        elif shape == "block" and a is not None and b is not None and c is not None:
            dims = f"{_n(a)}' x {_n(b)}\" x {_n(c)}\""
        elif shape == "slab" and a is not None and b is not None:
            dims = f'{_n(a)} SF x {_n(b)}" thick'
        elif shape == "box" and a is not None and b is not None and c is not None:
            dims = f'{_n(a)}" x {_n(b)}" x {_n(c)}"'
        inner = _join(dims, mix, sep=", ")
        return f"{name} ({inner})" if inner else name

    return _name(row, fallback)


def line_extended(line: ProposalLine) -> Decimal:
    """Quantity × unit price, to the cent; nothing on an excluded or unpriced line."""
    if line.status == "EXCLUDED" or line.qty is None or line.unit_price is None:
        return Decimal("0.00")
    return (_d(line.qty) * _d(line.unit_price)).quantize(_Q2)


def takeoff_lines(db: Session, section: EstimateSection) -> list[dict[str, Any]]:
    """
    The section's costed rows as proposal lines, in the section's order,
    each described from its own fields (describe_row).

    A row at no quantity — a library item nobody used, a garden-style pour at
    qty 0 — is not a line. The unit price is the row's stored sale over its
    quantity, to four places; a row not yet costed prices as nothing.
    """
    from app.models.estimate_section import SPOT_KINDS, WALL_KINDS
    from app.services.costing import cost_units

    out: list[dict[str, Any]] = []
    for i, u in enumerate(cost_units(db, section)):
        fallback = f"{section.name} {i + 1}"
        if section.kind in WALL_KINDS and section.kind not in SPOT_KINDS:
            out.extend(_wall_run_lines(db, u.row, section, fallback))
            continue
        qty = _d(u.quantity)
        if qty <= 0:
            continue
        sale = getattr(u.row, "calc_sale", None)
        price = (_d(sale) / qty).quantize(_Q4) if sale is not None else None
        out.append(
            {
                "source_table": u.row.__tablename__,
                "source_id": u.row.id,
                "source_part": None,
                "label": describe_row(db, u.row, section.kind, fallback=fallback),
                "qty": qty.quantize(Decimal("0.001")),
                # A spot footing sells per footing (sql/072) whatever the section's label says.
                "unit": "EA" if section.kind in SPOT_KINDS else section.unit,
                "unit_price": price,
            }
        )
    return out


def _wall_run_lines(db: Session, row: Any, section: EstimateSection, fallback: str) -> list[dict[str, Any]]:
    """
    A wall run as two lines (sql/081): the wall on its form feet at the
    wall's own sale, the footing under it on its length at the footing's —
    the split the costing keeps (sql/042), which always adds up to the run.
    A run with no footing is the wall line only; a run with no wall, the
    footing line only.
    """
    lines: list[dict[str, Any]] = []
    ff = _d(row.calc_form_ff)
    if ff > 0:
        sale = row.calc_wall_sale
        lines.append(
            {
                "source_table": row.__tablename__,
                "source_id": row.id,
                "source_part": "wall",
                "label": describe_row(db, row, section.kind, fallback=fallback),
                "qty": ff.quantize(Decimal("0.001")),
                "unit": "FF",
                "unit_price": (_d(sale) / ff).quantize(_Q4) if sale is not None else None,
            }
        )
    lf = _d(row.length_ft)
    if _d(row.calc_footing_sf) > 0 and lf > 0:
        sale = row.calc_footing_sale
        lines.append(
            {
                "source_table": row.__tablename__,
                "source_id": row.id,
                "source_part": "footing",
                "label": describe_footing(db, row, section, fallback=fallback),
                "qty": lf.quantize(Decimal("0.001")),
                "unit": "LF",
                "unit_price": (_d(sale) / lf).quantize(_Q4) if sale is not None else None,
            }
        )
    return lines


def job_label(project: Project | None, estimate: Estimate) -> str:
    if project is None:
        return estimate.name
    if project.job_number:
        return f"{project.name}  ·  {project.job_number}"
    return project.name


def _sections(db: Session, estimate_id: Any) -> list[EstimateSection]:
    return list(
        db.scalars(
            select(EstimateSection)
            .where(EstimateSection.estimate_id == estimate_id)
            .order_by(EstimateSection.sort_order, EstimateSection.created_at)
        ).all()
    )


def _proposal_sections(db: Session, proposal_id: Any) -> list[ProposalSection]:
    return list(
        db.scalars(
            select(ProposalSection)
            .where(ProposalSection.proposal_id == proposal_id)
            .order_by(ProposalSection.sort_order, ProposalSection.created_at)
        ).all()
    )


def _lines(db: Session, proposal_id: Any) -> list[ProposalLine]:
    return list(
        db.scalars(
            select(ProposalLine)
            .join(ProposalSection, ProposalSection.id == ProposalLine.proposal_section_id)
            .where(ProposalSection.proposal_id == proposal_id)
            .order_by(ProposalLine.proposal_section_id, ProposalLine.sort_order, ProposalLine.created_at)
        ).all()
    )


def copy_library(db: Session, proposal: Proposal) -> int:
    """Every block of the company's standing text, onto this proposal."""
    rows = db.scalars(
        select(ProposalLibraryItem).order_by(
            ProposalLibraryItem.block, ProposalLibraryItem.sort_order, ProposalLibraryItem.id
        )
    ).all()
    for r in rows:
        db.add(ProposalItem(proposal_id=proposal.id, block=r.block, sort_order=r.sort_order, text=r.text))
    return len(rows)


def seed_proposal(db: Session, estimate: Estimate) -> Proposal:
    """A new proposal for the estimate: header from the project, body from the takeoff, text from the library."""
    project = db.get(Project, estimate.project_id)
    proposal = Proposal(
        estimate_id=estimate.id,
        submitted_to=project.gc if project else None,
        job_label=job_label(project, estimate),
        location=project.location if project else None,
        intro=INTRO_DEFAULT,
        payment_terms=PAYMENT_DEFAULT,
        drawings=[{"discipline": d, "firm": None, "plan_date": None} for d in DISCIPLINES],
    )
    db.add(proposal)
    db.flush()

    for order, section in enumerate(_sections(db, estimate.id)):
        ps = ProposalSection(
            proposal_id=proposal.id, section_id=section.id, title=section.name, sort_order=(order + 1) * 10
        )
        db.add(ps)
        db.flush()
        for i, ln in enumerate(takeoff_lines(db, section)):
            db.add(
                ProposalLine(
                    proposal_section_id=ps.id,
                    sort_order=(i + 1) * 10,
                    description=ln["label"],
                    qty=ln["qty"],
                    unit=ln["unit"],
                    unit_price=ln["unit_price"],
                    source_table=ln["source_table"],
                    source_id=ln["source_id"],
                    source_part=ln["source_part"],
                )
            )
    copy_library(db, proposal)
    db.flush()
    return proposal


def refresh_from_estimate(db: Session, proposal: Proposal) -> dict[str, int]:
    """
    Pull the estimate onto the proposal again.

    A line with a source gets the row's current quantity, unit and price and
    keeps its description, status and notes. A row with no line yet becomes
    one, appended to its section; an estimate section with no proposal
    section yet becomes one, appended. A line whose row is gone, or at no
    quantity, is marked missing and left for someone to delete. Lines typed
    by hand are not touched.
    """
    psections = _proposal_sections(db, proposal.id)
    by_section = {ps.section_id: ps for ps in psections if ps.section_id is not None}
    lines = _lines(db, proposal.id)
    by_source = {
        (ln.source_table, ln.source_id, ln.source_part): ln for ln in lines if ln.source_id is not None
    }
    last_order: dict[Any, int] = {}
    for ln in lines:
        last_order[ln.proposal_section_id] = max(last_order.get(ln.proposal_section_id, 0), ln.sort_order)

    seen: set[tuple[str | None, Any, str | None]] = set()
    updated = added = added_sections = 0
    next_section_order = max((ps.sort_order for ps in psections), default=0)
    ps_by_id = {ps.id: ps for ps in psections}

    for section in _sections(db, proposal.estimate_id):
        ps = by_section.get(section.id)
        if ps is None:
            # The estimator filed this section's lines elsewhere and let the
            # seeded section go. New rows go where their siblings went.
            home = _home_of(db, section, lines)
            ps = ps_by_id.get(home) if home is not None else None
        if ps is None:
            next_section_order += 10
            ps = ProposalSection(
                proposal_id=proposal.id, section_id=section.id, title=section.name, sort_order=next_section_order
            )
            db.add(ps)
            db.flush()
            by_section[section.id] = ps
            added_sections += 1
        for ln in takeoff_lines(db, section):
            key = (ln["source_table"], ln["source_id"], ln["source_part"])
            seen.add(key)
            line = by_source.get(key)
            if line is None and ln["source_part"] == "wall":
                # A line seeded before sql/081 was the whole run. It becomes the
                # wall half and keeps its words; the footing half arrives beside it.
                line = by_source.pop((ln["source_table"], ln["source_id"], None), None)
                if line is not None:
                    line.source_part = "wall"
                    by_source[key] = line
            if line is None:
                order = last_order.get(ps.id, 0) + 10
                last_order[ps.id] = order
                db.add(
                    ProposalLine(
                        proposal_section_id=ps.id,
                        sort_order=order,
                        description=ln["label"],
                        qty=ln["qty"],
                        unit=ln["unit"],
                        unit_price=ln["unit_price"],
                        source_table=ln["source_table"],
                        source_id=ln["source_id"],
                        source_part=ln["source_part"],
                    )
                )
                added += 1
                continue
            changed = (
                _d(line.qty) != ln["qty"]
                or (line.unit_price is None) != (ln["unit_price"] is None)
                or (line.unit_price is not None and _d(line.unit_price) != ln["unit_price"])
                or line.unit != ln["unit"]
                or line.source_missing
            )
            line.qty = ln["qty"]
            line.unit = ln["unit"]
            line.unit_price = ln["unit_price"]
            line.source_missing = False
            if changed:
                updated += 1

    missing = 0
    for key, line in by_source.items():
        if key not in seen:
            line.source_missing = True
            missing += 1
    db.flush()
    return {"updated": updated, "added_lines": added, "added_sections": added_sections, "missing": missing}


def _home_of(db: Session, section: EstimateSection, lines: list[ProposalLine]) -> Any:
    """The proposal section holding most of the lines taken off in this estimate section, if any."""
    votes: dict[Any, int] = {}
    for ln in lines:
        if ln.source_table is None or ln.source_id is None:
            continue
        model = MODEL_BY_TABLE.get(ln.source_table)
        row = db.get(model, ln.source_id) if model is not None else None
        if row is not None and getattr(row, "section_id", None) == section.id:
            votes[ln.proposal_section_id] = votes.get(ln.proposal_section_id, 0) + 1
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]


def file_name(proposal: Proposal, project: Project | None, estimate: Estimate) -> str:
    """The playbook's name: `<Job Name> - Proposal - <Job #> - <YYYY-MM-DD>_<NN>.xlsx`."""
    parts = [(project.name if project else estimate.name).strip(), "Proposal"]
    if project is not None and project.job_number:
        parts.append(project.job_number.strip())
    parts.append(f"{proposal.proposal_date:%Y-%m-%d}_{proposal.rev:02d}")
    raw = " - ".join(parts) + ".xlsx"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw)


def source_label(db: Session, line: ProposalLine) -> str | None:
    """What the row behind a line calls itself today; None when there is no row."""
    if line.source_table is None or line.source_id is None:
        return None
    model = MODEL_BY_TABLE.get(line.source_table)
    if model is None:
        return None
    row = db.get(model, line.source_id)
    if row is None:
        return None
    label = row_label(row)
    return f"{label} · {line.source_part}" if line.source_part else label


def source_sale(db: Session, line: ProposalLine) -> Decimal | None:
    """
    What the row behind a line sells for in the estimate: the wall or the
    footing half of a wall run, else the whole row. None on a typed line or
    a row that is gone.
    """
    if line.source_table is None or line.source_id is None:
        return None
    model = MODEL_BY_TABLE.get(line.source_table)
    row = db.get(model, line.source_id) if model is not None else None
    if row is None:
        return None
    field = {"wall": "calc_wall_sale", "footing": "calc_footing_sale"}.get(line.source_part or "", "calc_sale")
    value = getattr(row, field, None)
    return _d(value).quantize(_Q2) if value is not None else None


def proposal_read(db: Session, proposal: Proposal) -> dict[str, Any]:
    """
    The whole proposal as the page and the workbook read it, totals and
    tie-outs included.

    A section's `estimate_sale` is what the rows filed in it sell for in the
    estimate, whatever section they were taken off in — so a section the
    estimator assembled from three still checks against the takeoff, and a
    typed line shows as money on top.
    """
    estimate = db.get(Estimate, proposal.estimate_id)
    project = db.get(Project, estimate.project_id) if estimate is not None else None
    est_sections = {s.id: s for s in _sections(db, proposal.estimate_id)}

    lines_by_section: dict[Any, list[ProposalLine]] = {}
    for ln in _lines(db, proposal.id):
        lines_by_section.setdefault(ln.proposal_section_id, []).append(ln)

    sections_out: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for ps in _proposal_sections(db, proposal.id):
        lines_out = []
        section_total = Decimal("0.00")
        sourced = Decimal("0.00")
        any_sourced = False
        for ln in lines_by_section.get(ps.id, []):
            ext = line_extended(ln)
            section_total += ext
            sale = source_sale(db, ln)
            if sale is not None:
                sourced += sale
                any_sourced = True
            lines_out.append(
                {
                    "id": ln.id,
                    "proposal_section_id": ln.proposal_section_id,
                    "sort_order": ln.sort_order,
                    "description": ln.description,
                    "qty": ln.qty,
                    "unit": ln.unit,
                    "status": ln.status,
                    "unit_price": ln.unit_price,
                    "extended": ext,
                    "source_table": ln.source_table,
                    "source_id": ln.source_id,
                    "source_part": ln.source_part,
                    "source_label": source_label(db, ln),
                    "source_missing": ln.source_missing,
                    "notes": ln.notes,
                }
            )
        est = est_sections.get(ps.section_id) if ps.section_id is not None else None
        est_sale = sourced if any_sourced else None
        sections_out.append(
            {
                "id": ps.id,
                "title": ps.title,
                "sort_order": ps.sort_order,
                "section_id": ps.section_id,
                "estimate_section_name": est.name if est is not None else None,
                "estimate_section_kind": est.kind if est is not None else None,
                "estimate_sale": est_sale,
                "total": section_total,
                "difference": (section_total - est_sale) if est_sale is not None else None,
                "line_count": len(lines_out),
                "lines": lines_out,
            }
        )
        total += section_total

    items: dict[str, list[dict[str, Any]]] = {b: [] for b in BLOCKS}
    for it in db.scalars(
        select(ProposalItem)
        .where(ProposalItem.proposal_id == proposal.id)
        .order_by(ProposalItem.block, ProposalItem.sort_order, ProposalItem.created_at)
    ).all():
        items.setdefault(it.block, []).append({"id": it.id, "sort_order": it.sort_order, "text": it.text})

    est_sale = (
        _d(estimate.calc_total_sale).quantize(_Q2)
        if estimate is not None and estimate.calc_total_sale is not None
        else None
    )
    return {
        "id": proposal.id,
        "estimate_id": proposal.estimate_id,
        "estimate_name": estimate.name if estimate is not None else None,
        "project_name": project.name if project is not None else None,
        "rev": proposal.rev,
        "proposal_date": proposal.proposal_date,
        "submitted_to": proposal.submitted_to,
        "attn": proposal.attn,
        "email": proposal.email,
        "phone": proposal.phone,
        "job_label": proposal.job_label,
        "location": proposal.location,
        "intro": proposal.intro,
        "payment_terms": proposal.payment_terms,
        "drawings": list(proposal.drawings or []),
        "notes": proposal.notes,
        "sections": sections_out,
        "items": items,
        "total": total,
        "estimate_sale": est_sale,
        "difference": (total - est_sale) if est_sale is not None else None,
        "file_name": file_name(proposal, project, estimate) if estimate is not None else "Proposal.xlsx",
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def library_read(db: Session) -> dict[str, list[dict[str, Any]]]:
    blocks: dict[str, list[dict[str, Any]]] = {b: [] for b in BLOCKS}
    for r in db.scalars(
        select(ProposalLibraryItem).order_by(
            ProposalLibraryItem.block, ProposalLibraryItem.sort_order, ProposalLibraryItem.id
        )
    ).all():
        blocks.setdefault(r.block, []).append({"id": r.id, "sort_order": r.sort_order, "text": r.text})
    return blocks
