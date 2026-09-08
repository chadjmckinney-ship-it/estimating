"""
Separately poured grade beams and continuous footings: the 02-Gd Beams tab,
formula by formula (sql/073).

The row (the tab's row 10) is a beam TYPE with a length: mix, L, W, H, top
bars, bottom bars, mid bars per side, stirrups at a spacing, L bars at a
spacing with a length each, and pilasters as a count of L" x W" blocks.

STEEL (W10). Top and bottom bars run the length; mid bars are typed per side
and doubled; stirrups are a hoop of 2(W + H) inches every `spacing`, with no
hook allowance (the mono slab's `calc_stirrup_lb` adds a foot of hooks, which
this tab does not, so it is not reused); L bars are one every `spacing` along
the beam, each `l_bars_length_ft` long. Bar weight is the catalog's
(bar_weights), where the tab reads (size/16)^2 x 10.680159 — the same tenth
of a percent named on walls and spot footings; `sheet_mode` swaps the tab's
constants back in. Pilaster steel is 3% of the pilaster's volume at steel's
0.2836 lb/in^3 (`pilaster_steel_pct`). Everything carries the section's rebar
waste; the tab wastes pilaster steel at its own 5% (K53), which only matters
on a job that has pilasters.

One quirk NOT reproduced: the tab's W10 opens `IF(P10 = 0, 0, ...)` — a beam
with no stirrup spacing has no steel at all, top and bottom bars included.
Here no spacing means no stirrups.

CONCRETE (X10). L x W/12 x H/12 / 27, plus the pilasters' volume rounded UP
to whole CY per row, all with the section's concrete waste.

FORM FEET. `calc_face_ff` is ONE face, L x H/12 — the tab's BB column, and
its I63 that every $/FF labor rate is priced against. `calc_contact_ff` is
both faces (BA), what wall ties and the form rental run off. Pilaster face
feet are (L" + W") x H / 144 per pilaster (BC).

EARTH. The tab digs a trench as deep as the beam is tall and as wide as it
is tall — L x H/12 x H/12 / 27 — plus the beam's own concrete, rounded to
whole CY per row (FT); it backfills the trench alone (FV). Reproduced as is.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.beam_run import BeamRun
from app.models.estimate_section import BEAM_KINDS, EstimateSection
from app.services.calc import _rate_numeric, _waste
from app.services.walls import bar_lb_per_ft, sheet_bar_lb_per_ft

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")

CU_IN_PER_CY = Decimal("46656")          # 1728 x 27, the all-inches pilaster block
STEEL_LB_PER_CU_IN = Decimal("0.2836")   # the tab's constant for pilaster steel
# The tab's stirrup weight per foot: (size/16)^2 x 3.145 x 0.2836 lb/in x 12.
_SHEET_STIRRUP_CONST = Decimal("3.145") * STEEL_LB_PER_CU_IN * Decimal("12")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def _lb_per_ft(db: Session, size: int | None, *, sheet: bool) -> Decimal:
    return sheet_bar_lb_per_ft(size) if sheet else bar_lb_per_ft(db, size)


def _stirrup_lb_per_ft(db: Session, size: int | None, *, sheet: bool) -> Decimal:
    if not size:
        return Decimal("0")
    if sheet:
        s = Decimal(str(size)) / Decimal("16")
        return s * s * _SHEET_STIRRUP_CONST
    return bar_lb_per_ft(db, size)


# ----------------------------------------------------------- geometry ----


def face_ff(length_ft: Any, height_in: Any) -> Decimal:
    """One face: L x H/12 (the tab's BB)."""
    return (_d(length_ft) * _d(height_in) / Decimal("12")).quantize(_Q4)


def contact_ff(length_ft: Any, height_in: Any) -> Decimal:
    """Both faces: L x H/12 x 2 (BA)."""
    return (face_ff(length_ft, height_in) * Decimal("2")).quantize(_Q4)


def pilaster_ff(count: Any, length_in: Any, width_in: Any, height_in: Any) -> Decimal:
    """(L" + W") x H / 144 per pilaster (BC)."""
    return (
        (_d(length_in) + _d(width_in)) * _d(height_in) / Decimal("144") * _d(count)
    ).quantize(_Q4)


def beam_cy(length_ft: Any, width_in: Any, height_in: Any) -> Decimal:
    """L x W/12 x H/12 / 27 — the tab's F x G/12 x H/324."""
    return _d(length_ft) * _d(width_in) / Decimal("12") * _d(height_in) / Decimal("324")


def pilaster_cy(count: Any, length_in: Any, width_in: Any, height_in: Any) -> Decimal:
    """ROUNDUP of the pilasters' volume in whole CY, per row (X10)."""
    vol = _d(count) * _d(length_in) * _d(width_in) * _d(height_in) / CU_IN_PER_CY
    return Decimal(math.ceil(vol)) if vol > 0 else Decimal("0")


def trench_cy(length_ft: Any, height_in: Any) -> Decimal:
    """L x H/12 x H/12 / 27 — the tab's F x H/324 x H/12."""
    h = _d(height_in)
    return _d(length_ft) * h / Decimal("324") * h / Decimal("12")


def excavate_cy(length_ft: Any, height_in: Any, concrete_cy: Any) -> Decimal:
    """ROUND(trench + the beam's own concrete) (FT)."""
    return Decimal(round(trench_cy(length_ft, height_in) + _d(concrete_cy)))


def backfill_cy(length_ft: Any, height_in: Any) -> Decimal:
    """ROUND(trench) (FV)."""
    return Decimal(round(trench_cy(length_ft, height_in)))


# --------------------------------------------------------------- steel ----


def bars_lb(db: Session, count: Any, size: int | None, length_ft: Any, *, sheet: bool = False) -> Decimal:
    """Longitudinal bars: count x L x lb/ft."""
    n = _d(count)
    if n <= 0 or not size:
        return Decimal("0")
    return n * _d(length_ft) * _lb_per_ft(db, size, sheet=sheet)


def stirrups_lb(
    db: Session, length_ft: Any, width_in: Any, height_in: Any, size: int | None, spacing_in: Any,
    *, sheet: bool = False,
) -> Decimal:
    """A hoop of 2(W + H) inches every `spacing` along the beam. No hooks — the tab has none."""
    sp = _d(spacing_in)
    if not size or sp <= 0:
        return Decimal("0")
    hoop_ft = Decimal("2") * (_d(width_in) + _d(height_in)) / Decimal("12")
    count = _d(length_ft) * Decimal("12") / sp
    return count * hoop_ft * _stirrup_lb_per_ft(db, size, sheet=sheet)


def l_bars_lb(
    db: Session, length_ft: Any, size: int | None, spacing_in: Any, each_ft: Any, *, sheet: bool = False
) -> Decimal:
    """One L bar every `spacing` along the beam, each `each_ft` long."""
    sp = _d(spacing_in)
    each = _d(each_ft)
    if not size or sp <= 0 or each <= 0:
        return Decimal("0")
    return _d(length_ft) * Decimal("12") / sp * each * _lb_per_ft(db, size, sheet=sheet)


def pilaster_steel_lb(count: Any, length_in: Any, width_in: Any, height_in: Any, pct: Decimal) -> Decimal:
    """Steel as a share of the pilaster's volume: in^3 x 0.2836 lb/in^3 x pct."""
    return _d(count) * _d(length_in) * _d(width_in) * _d(height_in) * STEEL_LB_PER_CU_IN * pct


# ------------------------------------------------------------- the row ----


def refresh_beam_run_calcs(
    db: Session, run: BeamRun, section: EstimateSection | None = None, *, sheet_mode: bool = False
) -> BeamRun:
    """Populate run.calc_* from the schedule. Caller commits."""
    if section is None:
        section = db.get(EstimateSection, run.section_id)
    if section is None:
        raise ValueError("section not found for beam run")

    kind = getattr(section, "kind", None)
    waste_c = _waste(section, db, "waste_concrete", "waste_concrete")
    waste_r = _waste(section, db, "waste_rebar", "waste_rebar")
    pil_pct = _rate_numeric(db, kind, "pilaster_steel_pct", Decimal("0.03"))

    L, W, H = _d(run.length_ft), _d(run.width_in), _d(run.height_in)

    run.calc_face_ff = face_ff(L, H).quantize(_Q3)
    run.calc_contact_ff = contact_ff(L, H).quantize(_Q3)
    run.calc_pilaster_ff = pilaster_ff(
        run.pilaster_count, run.pilaster_length_in, run.pilaster_width_in, H
    ).quantize(_Q3)

    cy = beam_cy(L, W, H) + pilaster_cy(run.pilaster_count, run.pilaster_length_in, run.pilaster_width_in, H)
    run.calc_concrete_cy = (cy * (Decimal("1") + waste_c)).quantize(_Q4)

    bars = (
        bars_lb(db, run.top_bars_count, run.top_bars_size, L, sheet=sheet_mode)
        + bars_lb(db, run.bottom_bars_count, run.bottom_bars_size, L, sheet=sheet_mode)
        + bars_lb(db, _d(run.mid_bars_count) * 2, run.mid_bars_size, L, sheet=sheet_mode)
        + stirrups_lb(db, L, W, H, run.stirrup_size, run.stirrup_spacing_in, sheet=sheet_mode)
        + l_bars_lb(db, L, run.l_bars_size, run.l_bars_spacing_in, run.l_bars_length_ft, sheet=sheet_mode)
    )
    pil = pilaster_steel_lb(run.pilaster_count, run.pilaster_length_in, run.pilaster_width_in, H, pil_pct)
    run.calc_total_rebar_lb = ((bars + pil) * (Decimal("1") + waste_r)).quantize(_Q3)

    run.calc_excavate_cy = excavate_cy(L, H, run.calc_concrete_cy).quantize(_Q3)
    run.calc_backfill_cy = backfill_cy(L, H).quantize(_Q3)
    return run


def refresh_section_beam_calcs(
    db: Session, section: EstimateSection, *, sheet_mode: bool = False
) -> int:
    runs = list(
        db.scalars(
            select(BeamRun)
            .where(BeamRun.section_id == section.id)
            .order_by(BeamRun.sort_order, BeamRun.created_at)
        ).all()
    )
    for run in runs:
        refresh_beam_run_calcs(db, run, section, sheet_mode=sheet_mode)
    return len(runs)


def section_beam_totals(db: Session, section_id: Any) -> dict[str, Any]:
    """Rollup for a beams section. Mirrors section_wall_totals."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS run_count,
              coalesce(sum(pilaster_count), 0)::int AS pilaster_count,
              coalesce(sum(length_ft), 0) AS total_length_ft,
              coalesce(sum(calc_contact_ff), 0) AS total_contact_ff,
              coalesce(sum(calc_face_ff), 0) AS total_face_ff,
              coalesce(sum(calc_pilaster_ff), 0) AS total_pilaster_ff,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_excavate_cy), 0) AS total_excavate_cy,
              coalesce(sum(calc_backfill_cy), 0) AS total_backfill_cy,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost,
              coalesce(sum(calc_sale), 0) AS total_sale
            FROM beam_runs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    lf = _d(out.get("total_length_ft"))
    ff = _d(out.get("total_face_ff"))
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    out["total_cost_per_unit"] = (cost / lf).quantize(_Q4) if lf > 0 else None
    out["total_sale_per_unit"] = (sale / lf).quantize(_Q4) if lf > 0 else None
    out["cost_per_ff"] = (cost / ff).quantize(_Q4) if ff > 0 else None
    out["sale_per_ff"] = (sale / ff).quantize(_Q4) if ff > 0 else None
    return out


def beam_drivers(db: Session, section_id: Any) -> dict[str, Decimal | int]:
    """The section's takeoff sums, for the three line sets."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS run_count,
              coalesce(sum(length_ft), 0) AS beam_lf,
              coalesce(sum(calc_contact_ff), 0) AS contact_ff,
              coalesce(sum(calc_face_ff), 0) AS face_ff,
              coalesce(sum(calc_pilaster_ff), 0) AS pilaster_ff,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_excavate_cy), 0) AS excavate_cy,
              coalesce(sum(calc_backfill_cy), 0) AS backfill_cy
            FROM beam_runs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    return {
        "run_count": int(row["run_count"] or 0),
        "beam_lf": _d(row["beam_lf"]),
        "contact_ff": _d(row["contact_ff"]),
        "face_ff": _d(row["face_ff"]),
        "pilaster_ff": _d(row["pilaster_ff"]),
        "total_rebar_lb": _d(row["total_rebar_lb"]),
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "excavate_cy": _d(row["excavate_cy"]),
        "backfill_cy": _d(row["backfill_cy"]),
    }


def is_beams(kind: str | None) -> bool:
    return kind in BEAM_KINDS
