"""
Labor + supervision for mono-slab estimates (Excel 04 LABOR / SUPERVISION).

Slab labor (sub by default when enabled=Y):
  Forming, Grading/Cables, Place & Finish, Wreck → $/SF × total SF
  Drops → $/FF × drops_ff
  Tie steel → $/TON × (rebar_lb / 2000)
  Excavation / hold-downs / labor add / extra hours → drivers or manual

Supervision:
  Super weeks = SF / 16000
  Super days  = weeks × 7
  Superintendent = days × $/day
  Foreman = days × $/day (0 qty until entered / same days if enabled)
  Expense + PM = same days as super × rate
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models.estimate_section import (
    COLUMN_KINDS,
    PAVING_KINDS,
    PIER_KINDS,
    WALL_KINDS,
)
from app.services.calc import _rate_numeric, _setting_numeric, section_kind
from app.services.price_book import priced_as


def _d(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def _pier_labor_drivers(db: Session, section_id: UUID, kind: str | None) -> dict[str, Any]:
    """
    Drivers for a piers section — counts, not areas.

    Supervision is the part worth reading twice. Every other assembly derives a
    duration from area (SF / 16,000 a week on the slab sheet, SF / 25,000 on
    paving). Piers has no area, so the workbook TYPES the days: 15 super, 10
    foreman. There is nothing to derive from, so the days are read back off the
    stored superintendent line — whatever the estimator entered — and
    everything downstream, including the equipment ladder, rides that.
    """
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS group_count,
              coalesce(sum(qty), 0)::int AS pier_count,
              coalesce(sum(calc_total_lf), 0) AS total_lf,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy
            FROM pier_groups
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    typed_days = db.execute(
        text(
            "SELECT qty FROM estimate_labor_lines "
            "WHERE section_id = :sid AND code = 'superintendent'"
        ),
        {"sid": str(section_id)},
    ).scalar()
    days = _d(typed_days)

    rebar = _d(row["total_rebar_lb"])
    days_per_week = _rate_numeric(db, kind, "labor_super_days_per_week", Decimal("7"))
    return {
        "kind": kind,
        "pour_count": int(row["group_count"] or 0),
        "pier_count": int(row["pier_count"] or 0),
        "total_sf": Decimal("0"),
        "total_lf": _d(row["total_lf"]),
        "drops_ff": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "paving_add": Decimal("0"),
        "total_rebar_lb": rebar,
        "tied_rebar_lb": rebar,
        "total_rebar_tons": (rebar / Decimal("2000")).quantize(Decimal("0.0001")),
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "total_slab_cy": Decimal("0"),
        "super_days": days,
        "super_weeks": (days / days_per_week).quantize(Decimal("0.0001"))
        if days_per_week > 0
        else Decimal("0"),
        "sf_per_week": Decimal("0"),
        "days_per_week": days_per_week,
        "super_days_are_typed": True,
    }


def labor_drivers(db: Session, section_id: UUID) -> dict[str, Any]:
    kind = section_kind(db, section_id)
    if kind in PIER_KINDS:
        return _pier_labor_drivers(db, section_id, kind)
    if kind in WALL_KINDS:
        return _wall_labor_drivers(db, section_id, kind)
    if kind in COLUMN_KINDS:
        return _column_labor_drivers(db, section_id, kind)

    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS pour_count,
              coalesce(sum(square_footage), 0) AS total_sf,
              -- Drops are grade beams (kind='drop') since sql/022.
              coalesce((
                  SELECT sum(gb.length_lf)
                  FROM grade_beam_details gb
                  JOIN mono_slabs dm ON dm.id = gb.mono_slab_id
                  WHERE dm.section_id = :sid AND gb.kind = 'drop'
              ), 0) AS drops_ff,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              -- Steel the crew actually ties: beam bars + slab mat. Support
              -- steel is the #3 that holds cables and mat up while they work —
              -- placing it IS the tying, so billing it again double-charges.
              coalesce(sum(
                  calc_total_rebar_lb - coalesce(calc_support_rebar_lb, 0)
              ), 0) AS tied_rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_slab_concrete_cy), 0) AS total_slab_cy,
              -- Paving (sql/036). The $/SF adder lands on LABOR ADJUSTMENT —
              -- column BA on the sheet — so it is a labor driver, not a
              -- material one.
              coalesce(sum(curb_lf), 0) AS curb_lf,
              coalesce(sum(square_footage * coalesce(paving_add_per_sf, 0)), 0)
                AS paving_add,
              -- Brick ledge (sql/029) is formed and stripped like a drop, so it
              -- carries its own labor line rather than riding the SF rates.
              coalesce((
                  SELECT sum(gb.length_lf)
                  FROM grade_beam_details gb
                  JOIN mono_slabs lm ON lm.id = gb.mono_slab_id
                  WHERE lm.section_id = :sid AND gb.kind = 'brick_ledge'
              ), 0) AS ledge_lf
            FROM mono_slabs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    sf = _d(row["total_sf"])
    rebar = _d(row["total_rebar_lb"])
    tied = _d(row["tied_rebar_lb"])
    tons = (rebar / Decimal("2000")).quantize(Decimal("0.0001")) if rebar else Decimal("0")

    kind = section_kind(db, section_id)
    sf_per_week = _rate_numeric(db, kind, "labor_super_sf_per_week", Decimal("16000"))
    days_per_week = _rate_numeric(db, kind, "labor_super_days_per_week", Decimal("7"))
    # Days come off the unrounded ratio. Rounding weeks first and multiplying
    # by seven multiplies the rounding error by seven too — six cents of
    # supervision on a 272,703 SF paving section, which is small but is the
    # kind of small that adds up across a job.
    raw_weeks = sf / sf_per_week if sf_per_week > 0 and sf > 0 else Decimal("0")
    weeks = raw_weeks.quantize(Decimal("0.0001"))
    days = (raw_weeks * days_per_week).quantize(Decimal("0.0001"))

    return {
        "kind": kind,
        "pour_count": int(row["pour_count"] or 0),
        "total_sf": sf,
        "drops_ff": _d(row["drops_ff"]),
        "ledge_lf": _d(row["ledge_lf"]),
        "curb_lf": _d(row["curb_lf"]),
        "paving_add": _d(row["paving_add"]),
        "total_rebar_lb": rebar,
        "tied_rebar_lb": tied,
        "total_rebar_tons": tons,
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "total_slab_cy": _d(row["total_slab_cy"]),
        "super_weeks": weeks,
        "super_days": days,
        "sf_per_week": sf_per_week,
        "days_per_week": days_per_week,
    }


def _rate(db: Session, kind: str | None, key: str, default: Decimal) -> Decimal:
    """Assembly rate first, company setting second (sql/035)."""
    return _rate_numeric(db, kind, key, default)


def _line(
    *,
    group: str,
    code: str,
    label: str,
    rate: float | Decimal,
    unit: str,
    qty: float | Decimal,
    formula: str,
    notes: str | None = None,
    enabled: bool = True,
    order: int,
) -> dict[str, Any]:
    q = _d(qty).quantize(Decimal("0.0001"))
    rt = _d(rate).quantize(Decimal("0.0001"))
    ext = (q * rt).quantize(Decimal("0.01")) if enabled else Decimal("0.00")
    return {
        "group_name": group,
        "code": code,
        "label": label,
        "enabled": enabled,
        "rate": rt,
        "unit": unit,
        "qty": q,
        "ext_cost": ext,
        "formula": formula,
        "notes": notes,
        "sort_order": order,
        "is_manual": False,
    }


def _supervision_lines(
    db: Session,
    kind: str | None,
    d: dict[str, Any],
    *,
    pm_days: float,
    foreman_days: float = 0.0,
) -> list[dict[str, Any]]:
    """
    The supervision ladder, shared by every assembly.

    Only the duration differs by sheet, and that is already in the drivers:
    paving supervises 25,000 SF a week where the slab sheet supervises 16,000.
    What does differ per sheet is who is on the job — the paving sheet carries
    no project manager, which is why pm_days is an argument rather than a rate.
    """
    days = float(d["super_days"])
    weeks = float(d["super_weeks"])
    typed = bool(d.get("super_days_are_typed"))
    return [
        _line(
            group="supervision", code="superintendent", label="SUPERINTENDENT",
            rate=_rate(db, kind, "labor_super_day_rate", Decimal("425")),
            unit="/DAY", qty=days,
            # Piers has no area, so there is nothing to derive a duration from
            # and the days are simply entered. Saying "SF / 0 weeks" there
            # would be a formula that cannot be true.
            formula=(
                "days entered — no area to derive a duration from"
                if typed
                else f"SF / {d['sf_per_week']} weeks × {d['days_per_week']} days × rate"
            ),
            notes=(
                "Everything downstream rides this, including the equipment ladder"
                if typed
                else f"{weeks:.4f} weeks"
            ),
            order=200,
        ),
        _line(
            group="supervision", code="foreman", label="FOREMAN",
            rate=_rate(db, kind, "labor_foreman_day_rate", Decimal("250")),
            # Most sheets leave this blank until somebody assigns a foreman.
            # The COLUMN sheet does not: `D93 = D92`, a foreman for every day
            # the superintendent is there. An argument rather than a rate, for
            # the same reason pm_days is one — it is who is on the job, not
            # what they cost.
            unit="/DAY", qty=foreman_days,
            formula=(
                "super days × rate" if foreman_days
                else "days × rate (set qty = super days when used)"
            ),
            notes=(
                None if foreman_days
                else "Default qty 0 — set equal to super days if needed"
            ),
            order=210,
        ),
        _line(
            group="supervision", code="expense", label="EXPENSE ALLOWANCE",
            rate=_rate(db, kind, "labor_expense_day_rate", Decimal("100")),
            unit="/DAY", qty=days, formula="super days × rate", order=220,
        ),
        _line(
            group="supervision", code="pm", label="PROJECT MANAGEMENT",
            rate=_rate(db, kind, "labor_pm_day_rate", Decimal("200")),
            unit="/DAY", qty=pm_days,
            formula="days entered" if typed else "super days × rate",
            notes=(
                None
                if pm_days or typed
                else "No PM carried on this assembly — set the days to add one"
            ),
            order=230,
        ),
    ]


def _mono_slab_labor_lines(
    db: Session, kind: str | None, d: dict[str, Any]
) -> list[dict[str, Any]]:
    sf = float(d["total_sf"])
    drops = float(d["drops_ff"])
    ledge = float(d["ledge_lf"])
    r_ledge = float(_rate(db, kind, "labor_brick_ledge_lf", Decimal("0")))

    # Tie steel covers the crew (or the sub) tying beam bars and slab mat.
    # Support steel is excluded: it is the #3 that holds the cables and mat up,
    # and placing it is the tying — billing it again charges twice for one pass.
    # An allowance per SF can still carry the first light steel; 0 bills every
    # ton. (sql/027 set 0.35 to reproduce the workbook, whose tonnage included
    # padding in the beams; sql/032 moved it back to 0 once that padding was
    # separated out. Uncheck the line entirely when a sub's price includes it.)
    free_lb_per_sf = _rate_numeric(db, kind, "labor_tie_steel_free_lb_per_sf", Decimal("0"))
    tied_lb = _d(d["tied_rebar_lb"])
    allowance_lb = _d(d["total_sf"]) * free_lb_per_sf
    billable_lb = max(Decimal("0"), tied_lb - allowance_lb)
    billable_tons = float((billable_lb / Decimal("2000")).quantize(Decimal("0.0001")))

    return [
        _line(group="labor", code="forming", label="FORMING",
              rate=_rate(db, kind, "labor_forming_sf", Decimal("0.45")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=10),
        _line(group="labor", code="grading", label="GRADING / CABLES",
              rate=_rate(db, kind, "labor_grading_sf", Decimal("0.70")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=20),
        _line(group="labor", code="place_finish", label="PLACE AND FINISH",
              rate=_rate(db, kind, "labor_place_finish_sf", Decimal("0.55")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=30),
        _line(group="labor", code="wreck", label="WRECK AND CLEAN UP",
              rate=_rate(db, kind, "labor_wreck_sf", Decimal("0.20")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=40),
        _line(group="labor", code="drops", label="DROPS",
              rate=_rate(db, kind, "labor_drops_ff", Decimal("8")),
              unit="/FF", qty=drops, formula="drops_ff × rate", order=50),
        _line(group="labor", code="brick_ledge", label="BRICK LEDGE", rate=r_ledge,
              unit="/LF", qty=ledge, formula="brick_ledge_lf × rate",
              notes=None if r_ledge else "Set labor_brick_ledge_lf to price this",
              order=55),
        _line(group="labor", code="labor_add", label="LABOR ADD", rate=0, unit="LS",
              qty=0, formula="manual / pour labor adds (later)",
              notes="Enter total $ or leave 0", order=60),
        _line(group="labor", code="excavation", label="EXCAVATION ADD",
              rate=_rate(db, kind, "labor_excavation_cy", Decimal("12")),
              unit="/CY", qty=0, formula="dirt CY (manual / later from dirt calc)",
              notes="Qty starts at 0 until dirt takeoff", order=70),
        _line(group="labor", code="hold_downs", label="HOLD DOWNS / FTGS",
              rate=_rate(db, kind, "labor_hold_down_ea", Decimal("100")),
              unit="/EA", qty=0,
              formula="hold-down count (manual / pour field later)", order=80),
        _line(
            group="labor", code="tie_steel", label="TIE STEEL",
            rate=_rate(db, kind, "labor_tie_steel_ton", Decimal("450")),
            unit="/TON", qty=billable_tons,
            formula=(
                "((beam + slab steel − total_sf × free_lb_per_sf) / 2000) × rate"
                if free_lb_per_sf > 0
                else "(beam + slab steel / 2000) × rate"
            ),
            notes=(
                f"Beam + slab steel {tied_lb:,.0f} lb of {d['total_rebar_lb']:,.0f} lb "
                f"— support steel excluded. First {free_lb_per_sf} lb/SF carried "
                f"({allowance_lb:,.0f} lb), leaving {billable_lb:,.0f} lb billable"
                if free_lb_per_sf > 0
                else f"Beam + slab steel {tied_lb:,.0f} lb of {d['total_rebar_lb']:,.0f} lb "
                f"— support steel excluded (it is placed, not tied separately)"
            ),
            order=90,
        ),
        _line(group="labor", code="extra_hours", label="EXTRA HOURS", rate=0,
              unit="LS", qty=0, formula="manual lump sum", order=100),
    ]


def _paving_labor_lines(
    db: Session, kind: str | None, d: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    10-PAVING rows 61–67.

    Three things are gone against the slab sheet and two are new. Gone: the
    GRADING / CABLES line (there are no cables and no beam cage to grade
    around), DROPS, and TIE STEEL — paving prices its steel labor per pound
    rather than per ton. New: CURB, priced per LF, and a LABOR ADJUSTMENT that
    carries the per-area $/SF adder.
    """
    sf = float(d["total_sf"])
    curb = float(d["curb_lf"])
    steel_lb = float(d["total_rebar_lb"])
    add = _d(d["paving_add"])
    r_curb = float(_rate(db, kind, "labor_curb_lf", Decimal("0")))
    r_rebar = float(_rate(db, kind, "labor_rebar_lb", Decimal("0")))

    return [
        _line(group="labor", code="forming", label="FORMING",
              rate=_rate(db, kind, "labor_forming_sf", Decimal("0.30")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=10),
        _line(group="labor", code="place_finish", label="PLACE AND FINISH",
              rate=_rate(db, kind, "labor_place_finish_sf", Decimal("0.55")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=30),
        _line(group="labor", code="wreck", label="WRECK AND CLEAN UP",
              rate=_rate(db, kind, "labor_wreck_sf", Decimal("0.15")),
              unit="/SF", qty=sf, formula="total_sf × rate", order=40),
        _line(group="labor", code="labor_add", label="LABOR ADJUSTMENT",
              rate=1, unit="LS", qty=add,
              formula="Σ area SF × that area's paving add $/SF",
              notes=(
                  None if add
                  else "Set a paving add $/SF on an area to carry an adjustment"
              ),
              order=60),
        _line(group="labor", code="rebar", label="REBAR", rate=r_rebar, unit="/LB",
              qty=steel_lb, formula="total steel lb × rate",
              notes=None if r_rebar else "Set labor_rebar_lb to price placing steel",
              order=65),
        _line(group="labor", code="curb", label="CURB", rate=r_curb, unit="/LF",
              qty=curb, formula="curb_lf × rate",
              notes=None if r_curb else "Set labor_curb_lf to price curb labor",
              order=70),
        _line(group="labor", code="extra_hours", label="EXTRA HOURS", rate=0,
              unit="LS", qty=0, formula="manual lump sum", order=100),
    ]


def _pier_labor_lines(
    db: Session, kind: str | None, d: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    01-Piers rows 57–63. Labor is priced **per pier**, not per square foot.

    Nothing here is an area rate, which is the whole point: layout, place and
    finish, and cleanup are $50 a pier apiece. Tie steel bills every pound —
    a pier cage has no support-steel allowance to carve out, so the mono-slab
    exclusion does not apply.
    """
    n = float(d["pier_count"])
    cy = float(d["total_concrete_cy"])
    tons = float(d["total_rebar_tons"])
    r_cap = float(_rate(db, kind, "labor_pier_cap_ea", Decimal("60")))
    r_exc = float(_rate(db, kind, "labor_excavation_cy", Decimal("0")))

    return [
        _line(group="labor", code="layout", label="LAYOUT",
              rate=_rate(db, kind, "labor_layout_ea", Decimal("50")),
              unit="/EA", qty=n, formula="piers × rate", order=10),
        _line(group="labor", code="place_finish", label="PLACE & FINISH",
              rate=_rate(db, kind, "labor_place_finish_ea", Decimal("50")),
              unit="/EA", qty=n, formula="piers × rate", order=20),
        _line(group="labor", code="cleanup", label="CLEANUP",
              rate=_rate(db, kind, "labor_cleanup_ea", Decimal("50")),
              unit="/EA", qty=n, formula="piers × rate", order=30),
        _line(group="labor", code="excavation", label="EXCAVATION", rate=r_exc,
              unit="/CY", qty=cy, formula="concrete CY × rate",
              notes=None if r_exc else "Set labor_excavation_cy to price spoil handling",
              order=40),
        _line(group="labor", code="tie_steel", label="TIE STEEL",
              rate=_rate(db, kind, "labor_tie_steel_ton", Decimal("450")),
              unit="/TON", qty=tons,
              formula="total steel lb / 2000 × rate",
              notes=f"All {d['total_rebar_lb']:,.0f} lb — a pier cage carries no "
                    f"support-steel allowance to exclude",
              order=50),
        _line(group="labor", code="pier_caps", label="PIER CAPS", rate=r_cap,
              unit="/EA", qty=0, formula="cap count (manual)",
              notes="Qty starts at 0 — enter the caps this job actually has",
              order=60),
        _line(group="labor", code="extra_hours", label="EXTRA HOURS", rate=0,
              unit="LS", qty=0, formula="manual lump sum", order=70),
    ]




def _wall_labor_drivers(db: Session, section_id: UUID, kind: str | None) -> dict[str, Any]:
    """
    Walls, like piers, TYPE their supervision days rather than deriving them.

    A wall job's duration is set by pour sequence and cure, not by area, so
    `labor_super_sf_per_week` is 0 for this assembly and the days are read back
    off the stored superintendent line — whatever the estimator entered. The
    equipment ladder rides that same number.
    """
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS run_count,
              coalesce(sum(length_ft), 0) AS wall_lf,
              coalesce(sum(calc_form_ff), 0) AS form_ff,
              coalesce(sum(calc_footing_sf), 0) AS footing_sf,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_excavate_cy), 0) AS excavate_cy,
              coalesce(sum(calc_backfill_cy), 0) AS backfill_cy,
              coalesce(sum(calc_drain_lf), 0) AS drain_lf
            FROM wall_runs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    typed_days = db.execute(
        text(
            "SELECT qty FROM estimate_labor_lines "
            "WHERE section_id = :sid AND code = 'superintendent'"
        ),
        {"sid": str(section_id)},
    ).scalar()
    days = _d(typed_days)
    rebar = _d(row["total_rebar_lb"])
    days_per_week = _rate_numeric(db, kind, "labor_super_days_per_week", Decimal("7"))
    return {
        "kind": kind,
        "pour_count": int(row["run_count"] or 0),
        "pier_count": 0,
        "wall_lf": _d(row["wall_lf"]),
        "form_ff": _d(row["form_ff"]),
        "footing_sf": _d(row["footing_sf"]),
        "excavate_cy": _d(row["excavate_cy"]),
        "backfill_cy": _d(row["backfill_cy"]),
        "drain_lf": _d(row["drain_lf"]),
        "total_sf": Decimal("0"),
        "total_lf": Decimal("0"),
        "drops_ff": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "paving_add": Decimal("0"),
        "total_rebar_lb": rebar,
        # A wall cage has no support-steel allowance to carve out, same as a
        # pier: every pound is tied.
        "tied_rebar_lb": rebar,
        "total_rebar_tons": (rebar / Decimal("2000")).quantize(Decimal("0.0001")),
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "total_slab_cy": Decimal("0"),
        "super_days": days,
        "super_weeks": (days / days_per_week).quantize(Decimal("0.0001"))
        if days_per_week > 0
        else Decimal("0"),
        "sf_per_week": Decimal("0"),
        "days_per_week": days_per_week,
        "super_days_are_typed": True,
    }


def _column_labor_drivers(
    db: Session, section_id: UUID, kind: str | None
) -> dict[str, Any]:
    """
    Columns derive their duration from a COUNT, on a FIVE-day week (sql/045).

    Every other assembly either divides an area (slab SF/16,000, paving
    SF/25,000, both times seven) or types the days outright (piers, walls).
    07-COLUMNS does neither: `C92 = D54/20` is columns per week and `D92 =
    C92*5` is a five-day week. A column crew is not on site seven days running,
    and 68 columns is a duration whatever their size.

    Quantized once, in services/columns.super_days — rounding the weeks and
    then multiplying is a double round, and that is what cost the mono slab
    eight cents.
    """
    from app.services.columns import super_days as _column_super_days

    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS type_count,
              coalesce(sum(qty), 0)::int AS column_count,
              coalesce(sum(calc_form_sf), 0) AS form_sf,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_chamfer_lf), 0) AS chamfer_lf
            FROM column_types
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    days = _column_super_days(db, section_id, kind)
    days_per_week = _rate_numeric(db, kind, "labor_super_days_per_week", Decimal("5"))
    per_week = _rate_numeric(db, kind, "columns_per_super_week", Decimal("20"))
    rebar = _d(row["total_rebar_lb"])
    return {
        "kind": kind,
        "pour_count": int(row["type_count"] or 0),
        "pier_count": 0,
        "column_count": int(row["column_count"] or 0),
        "form_sf": _d(row["form_sf"]),
        "chamfer_lf": _d(row["chamfer_lf"]),
        "wall_lf": Decimal("0"),
        "form_ff": Decimal("0"),
        "footing_sf": Decimal("0"),
        "excavate_cy": Decimal("0"),
        "backfill_cy": Decimal("0"),
        "drain_lf": Decimal("0"),
        "total_sf": _d(row["form_sf"]),
        "total_lf": Decimal("0"),
        "drops_ff": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "paving_add": Decimal("0"),
        "total_rebar_lb": rebar,
        # A column cage carries no support-steel allowance: every pound of it
        # is tied by hand, the same call piers and walls made.
        "tied_rebar_lb": rebar,
        "total_rebar_tons": (rebar / Decimal("2000")).quantize(Decimal("0.0001")),
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "total_slab_cy": Decimal("0"),
        "super_days": days,
        # The sheet puts a foreman on for every superintendent day (D93 = D92).
        "foreman_days": days,
        "super_weeks": (days / days_per_week).quantize(Decimal("0.0001"))
        if days_per_week > 0
        else Decimal("0"),
        "sf_per_week": per_week,
        "days_per_week": days_per_week,
        "super_days_are_typed": False,
    }


def _column_labor_lines(
    db: Session, kind: str | None, d: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    07-COLUMNS rows 82–87.

    Five rates run off FORM CONTACT AREA and one off tonnage. BUILD-UP is the
    line no other assembly has — assembling the form box around the cage before
    anything is poured — and on the sheet it is the ONE line already driven by
    the honest perimeter figure while forming, place, wreck and rub all ride a
    cross-section number that is 15.9% light. Here they all ride the same area,
    which is what makes this assembly read above the sheet.

    There is no footing line: a column lands on a pier cap or a footing that
    belongs to another section, and pricing it here would bill it twice.
    """
    sf = float(d["form_sf"])
    tons = float(d["total_rebar_tons"])

    return [
        _line(group="labor", code="build_up", label="BUILD-UP",
              rate=_rate(db, kind, "labor_build_up_sf", Decimal("0.5")),
              unit="/SF", qty=sf, formula="form SF × rate",
              notes="Assembling the form box — no slab equivalent", order=10),
        _line(group="labor", code="forming", label="FORMING",
              rate=_rate(db, kind, "labor_forming_sf", Decimal("2.5")),
              unit="/SF", qty=sf, formula="form SF × rate", order=20),
        _line(group="labor", code="place_finish", label="PLACE AND FINISH",
              rate=_rate(db, kind, "labor_place_finish_sf", Decimal("1.25")),
              unit="/SF", qty=sf, formula="form SF × rate", order=30),
        _line(group="labor", code="wreck", label="WRECK AND CLEAN UP",
              rate=_rate(db, kind, "labor_wreck_sf", Decimal("0.5")),
              unit="/SF", qty=sf, formula="form SF × rate", order=40),
        _line(group="labor", code="rub_patch", label="RUB AND PATCH",
              rate=_rate(db, kind, "labor_rub_patch_sf", Decimal("0.25")),
              unit="/SF", qty=sf, formula="form SF × rate",
              notes="What you do to a column face once the forms come off",
              order=50),
        _line(group="labor", code="tie_steel", label="TIE STEEL",
              rate=_rate(db, kind, "labor_tie_steel_ton", Decimal("450")),
              unit="/TON", qty=tons, formula="total steel lb / 2000 × rate",
              notes=f"All {d['total_rebar_lb']:,.0f} lb — a column cage carries "
                    "no support-steel allowance to carve out",
              order=60),
    ]


def _wall_labor_lines(
    db: Session, kind: str | None, d: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    06-Walls & Footings rows 66–75.

    Three rates run off FORM FEET (forming, place & finish, wreck) and one more
    that no other assembly has — RUB AND PATCH, which is what you do to a wall
    face after the forms come off and is meaningless on a slab.

    The footing is priced per SQUARE FOOT OF FOOTING, not per form foot: it is
    a flat pour in a trench, and its labor has nothing to do with the wall
    above it.

    Excavate, backfill and the french drain all come off the takeoff's own
    stored quantities rather than being re-derived here.
    """
    ff = float(d["form_ff"])
    ftg_sf = float(d["footing_sf"])
    tons = float(d["total_rebar_tons"])
    exc = float(d["excavate_cy"])
    bkf = float(d["backfill_cy"])
    drain = float(d["drain_lf"])

    return [
        _line(group="labor", code="footings", label="FOOTINGS",
              rate=_rate(db, kind, "labor_footings_sf", Decimal("8")),
              unit="/SF", qty=ftg_sf, formula="footing SF × rate",
              notes="Per SF of footing plan area, not per form foot", order=10),
        _line(group="labor", code="forming", label="FORMING",
              rate=_rate(db, kind, "labor_forming_sf", Decimal("3.5")),
              unit="/FF", qty=ff, formula="form FF × rate", order=20),
        _line(group="labor", code="place_finish", label="PLACE AND FINISH",
              rate=_rate(db, kind, "labor_place_finish_sf", Decimal("3.5")),
              unit="/FF", qty=ff, formula="form FF × rate", order=30),
        _line(group="labor", code="wreck", label="WRECK AND CLEAN UP",
              rate=_rate(db, kind, "labor_wreck_sf", Decimal("1")),
              unit="/FF", qty=ff, formula="form FF × rate", order=40),
        _line(group="labor", code="rub_patch", label="RUB AND PATCH",
              rate=_rate(db, kind, "labor_rub_patch_sf", Decimal("0.25")),
              unit="/FF", qty=ff, formula="form FF × rate",
              notes="A wall finish operation — no slab equivalent", order=50),
        _line(group="labor", code="tie_steel", label="TIE STEEL",
              rate=_rate(db, kind, "labor_tie_steel_ton", Decimal("450")),
              unit="/TON", qty=tons, formula="total steel lb / 2000 × rate",
              notes=f"All {d['total_rebar_lb']:,.0f} lb — a wall cage carries no "
                    f"support-steel allowance to exclude",
              order=60),
        _line(group="labor", code="french_drains", label="FRENCH DRAINS",
              rate=_rate(db, kind, "labor_french_drain_lf", Decimal("10")),
              unit="/LF", qty=drain, formula="drained LF × rate",
              notes="Installation; the pipe itself is a forming-package line",
              order=70),
        _line(group="labor", code="excavate", label="EXCAVATE",
              rate=_rate(db, kind, "labor_excavate_cy", Decimal("12")),
              unit="/CY", qty=exc, formula="excavation CY × rate", order=80),
        _line(group="labor", code="backfill", label="BACKFILL",
              rate=_rate(db, kind, "labor_backfill_cy", Decimal("8")),
              unit="/CY", qty=bkf, formula="backfill CY × rate", order=90),
        _line(group="labor", code="extra_hours", label="EXTRA HOURS", rate=0,
              unit="LS", qty=0, formula="manual lump sum", order=100),
    ]


def calc_labor_materials(db: Session, section_id: UUID) -> dict[str, Any]:
    """A price gate (sql/049): every labor rate below prices from the
    estimate's sheet. See services/price_book.py."""
    with priced_as(db, _estimate_id_of(db, section_id)):
        return _calc_labor_materials(db, section_id)


def _estimate_id_of(db: Session, section_id: UUID):
    return db.execute(
        text("SELECT estimate_id FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}
    ).scalar()


def _calc_labor_materials(db: Session, section_id: UUID) -> dict[str, Any]:
    """Build labor + supervision line dicts (not yet stored)."""
    d = labor_drivers(db, section_id)
    # Every workbook sheet carries its own rates AND its own set of lines; the
    # section's kind picks both. Paving forms at $0.30/SF where the slab sheet
    # is $0.45 (sql/035), and has no grading line at all (sql/036).
    kind = section_kind(db, section_id)
    is_paving = kind in PAVING_KINDS
    is_piers = kind in PIER_KINDS

    if is_piers:
        lines: list[dict[str, Any]] = _pier_labor_lines(db, kind, d)
    elif kind in WALL_KINDS:
        lines = _wall_labor_lines(db, kind, d)
    elif kind in COLUMN_KINDS:
        lines = _column_labor_lines(db, kind, d)
    elif is_paving:
        lines = _paving_labor_lines(db, kind, d)
    else:
        lines = _mono_slab_labor_lines(db, kind, d)

    # Where supervision is TYPED, nothing in it is derived — including the PM.
    # Piers types 10 PM days and walls types none, and neither is a function of
    # the superintendent's days; deriving one put $2,000 on LBJ's walls that
    # the sheet does not carry. Keyed off the driver rather than a list of
    # kinds, so the next typed assembly cannot fall through to the wrong branch.
    #
    # Paving carries no PM at all — the row is there with no days.
    if d.get("super_days_are_typed") or is_paving:
        pm_days = 0.0
    else:
        pm_days = float(d["super_days"])
    lines += _supervision_lines(
        db, kind, d, pm_days=pm_days,
        foreman_days=float(d.get("foreman_days") or 0),
    )

    labor_cost = sum(
        (_d(ln["ext_cost"]) for ln in lines if ln["group_name"] == "labor"),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    super_cost = sum(
        (_d(ln["ext_cost"]) for ln in lines if ln["group_name"] == "supervision"),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    total = (labor_cost + super_cost).quantize(Decimal("0.01"))
    cpsf = (total / d["total_sf"]).quantize(Decimal("0.0001")) if d["total_sf"] > 0 else None

    return {
        "drivers": d,
        "lines": lines,
        "total_labor_cost": labor_cost,
        "total_supervision_cost": super_cost,
        "total_cost": total,
        "cost_per_sf": cpsf,
        "stored": False,
        "refreshed_at": None,
    }


def refresh_and_store_labor(db: Session, section_id: UUID) -> dict[str, Any]:
    from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary

    data = calc_labor_materials(db, section_id)
    drivers = data["drivers"]
    lines = data["lines"]

    live_codes = {ln["code"] for ln in lines}
    existing = {
        r.code: r
        for r in db.scalars(
            select(EstimateLaborLine).where(EstimateLaborLine.section_id == section_id)
        ).all()
    }
    manuals = {c: r for c, r in existing.items() if r.is_manual and c in live_codes}

    db.execute(
        delete(EstimateLaborLine).where(
            EstimateLaborLine.section_id == section_id,
            EstimateLaborLine.is_manual.is_(False),
        )
    )
    # A section that changes kind changes line set. Drop what the new set does
    # not have, manual or not, so a paving section cannot keep billing a TIE
    # STEEL line from the slab set it used to be in.
    stale = [c for c in existing if c not in live_codes]
    if stale:
        db.execute(
            delete(EstimateLaborLine).where(
                EstimateLaborLine.section_id == section_id,
                EstimateLaborLine.code.in_(stale),
            )
        )
    db.flush()

    now = datetime.now(timezone.utc)
    for ln in lines:
        if ln["code"] in manuals:
            m = manuals[ln["code"]]
            # keep rate/qty/enabled for manual; refresh formula label
            m.formula = ln.get("formula")
            # Notes explain the line, not the number, so a manual override
            # should not freeze an explanation that has since changed.
            m.notes = ln.get("notes")
            m.label = ln.get("label") or m.label
            m.unit = ln.get("unit") or m.unit
            m.group_name = ln["group_name"]
            m.sort_order = ln["sort_order"]
            if m.enabled:
                m.ext_cost = (_d(m.qty) * _d(m.rate)).quantize(Decimal("0.01"))
            else:
                m.ext_cost = Decimal("0.00")
            m.updated_at = now
            continue

        # Preserve the on/off toggle, but take the rate from system_settings:
        # a non-manual line is by definition tracking the company default, so
        # keeping prev.rate here would make settings changes unreachable.
        # User rate edits arrive with mark_manual=True and land in `manuals`.
        prev = existing.get(ln["code"])
        enabled = prev.enabled if prev is not None else ln["enabled"]
        rate = ln["rate"]
        # qty always recalculated for non-manual (except we already skipped manuals)
        qty = ln["qty"]
        # Special: foreman keeps previous qty if user set it once without is_manual
        if ln["code"] == "foreman" and prev is not None and prev.qty and prev.qty > 0:
            qty = prev.qty
        ext = (_d(qty) * _d(rate)).quantize(Decimal("0.01")) if enabled else Decimal("0.00")

        db.add(
            EstimateLaborLine(
                section_id=section_id,
                group_name=ln["group_name"],
                code=ln["code"],
                label=ln["label"],
                enabled=enabled,
                rate=_d(rate),
                unit=ln["unit"],
                qty=_d(qty),
                ext_cost=ext,
                formula=ln.get("formula"),
                notes=ln.get("notes"),
                sort_order=ln["sort_order"],
                is_manual=False,
            )
        )

    db.flush()
    all_rows = list(
        db.scalars(
            select(EstimateLaborLine)
            .where(EstimateLaborLine.section_id == section_id)
            .order_by(EstimateLaborLine.sort_order)
        ).all()
    )
    labor_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "labor"), Decimal("0")
    ).quantize(Decimal("0.01"))
    super_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "supervision"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (labor_cost + super_cost).quantize(Decimal("0.01"))
    cpsf = (
        (total / drivers["total_sf"]).quantize(Decimal("0.0001"))
        if drivers["total_sf"] > 0
        else None
    )

    summary = db.get(EstimateLaborSummary, section_id)
    if summary is None:
        summary = EstimateLaborSummary(section_id=section_id)
        db.add(summary)
    summary.pour_count = drivers["pour_count"]
    summary.total_sf = drivers["total_sf"]
    summary.drops_ff = drivers["drops_ff"]
    summary.total_rebar_lb = drivers["total_rebar_lb"]
    summary.total_rebar_tons = drivers["total_rebar_tons"]
    summary.super_weeks = drivers["super_weeks"]
    summary.super_days = drivers["super_days"]
    summary.total_labor_cost = labor_cost
    summary.total_supervision_cost = super_cost
    summary.total_cost = total
    summary.cost_per_sf = cpsf
    summary.refreshed_at = now

    from app.services.costing import refresh_pour_costs_for_id
    refresh_pour_costs_for_id(db, section_id)

    db.commit()
    return load_stored_labor(db, section_id)


def load_stored_labor(db: Session, section_id: UUID) -> dict[str, Any] | None:
    from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary

    summary = db.get(EstimateLaborSummary, section_id)
    if summary is None:
        return None

    rows = list(
        db.scalars(
            select(EstimateLaborLine)
            .where(EstimateLaborLine.section_id == section_id)
            .order_by(EstimateLaborLine.sort_order, EstimateLaborLine.code)
        ).all()
    )
    lines = [
        {
            "id": str(r.id),
            "group_name": r.group_name,
            "code": r.code,
            "label": r.label,
            "enabled": r.enabled,
            "rate": r.rate,
            "unit": r.unit,
            "qty": r.qty,
            "ext_cost": r.ext_cost,
            "formula": r.formula or "",
            "notes": r.notes,
            "sort_order": r.sort_order,
            "is_manual": r.is_manual,
        }
        for r in rows
    ]
    # The summary table predates paving, so these two are read live rather
    # than stored. They are pour columns, so they cannot go stale between
    # a refresh and a read the way a derived figure could.
    kind = section_kind(db, section_id)
    extra = db.execute(
        text(
            "SELECT coalesce(sum(curb_lf), 0) AS curb_lf, "
            "       coalesce(sum(square_footage * coalesce(paving_add_per_sf, 0)), 0)"
            "         AS paving_add, "
            "       (SELECT coalesce(sum(qty), 0) FROM pier_groups WHERE section_id = :sid)"
            "         AS pier_count, "
            "       (SELECT coalesce(sum(calc_total_lf), 0) FROM pier_groups"
            "         WHERE section_id = :sid) AS pier_lf "
            "FROM mono_slabs WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    drivers: dict[str, Any] = {
        "kind": kind,
        "pour_count": summary.pour_count,
        "pier_count": int(extra["pier_count"] or 0),
        "total_lf": _d(extra["pier_lf"]),
        "super_days_are_typed": kind in PIER_KINDS or kind in WALL_KINDS,
        "total_sf": summary.total_sf,
        "drops_ff": summary.drops_ff,
        "curb_lf": _d(extra["curb_lf"]),
        "paving_add": _d(extra["paving_add"]),
        "total_rebar_lb": summary.total_rebar_lb,
        "total_rebar_tons": summary.total_rebar_tons,
        "super_weeks": summary.super_weeks,
        "super_days": summary.super_days,
    }

    # The dict above is assembled from the summary TABLE, which carries the
    # columns a mono slab needs and nothing else — so an assembly that takes
    # off into its own table (walls, columns) loses its geometry on the way
    # back out, and the section page renders a dash where the count belongs.
    #
    # The fields overlaid here are the ones the SCREEN explains itself with:
    # a columns header says "68 ÷ 20 a week × 5", which needs both divisors and
    # not just the answer. Nothing already in the dict is touched — every
    # stored cost, day and total above survives — so this can only add.
    if kind in WALL_KINDS or kind in COLUMN_KINDS:
        live = labor_drivers(db, section_id)
        for key in (
            "column_count", "form_sf", "chamfer_lf",
            "sf_per_week", "days_per_week", "foreman_days",
            "wall_lf", "form_ff", "footing_sf",
        ):
            if key in live:
                drivers[key] = live[key]

    return {
        "drivers": drivers,
        "lines": lines,
        "total_labor_cost": summary.total_labor_cost,
        "total_supervision_cost": summary.total_supervision_cost,
        "total_cost": summary.total_cost,
        "cost_per_sf": summary.cost_per_sf,
        "stored": True,
        "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
    }


def get_or_refresh_labor(db: Session, section_id: UUID) -> dict[str, Any]:
    stored = load_stored_labor(db, section_id)
    if stored is not None:
        return stored
    return refresh_and_store_labor(db, section_id)


def update_labor_line(
    db: Session,
    section_id: UUID,
    code: str,
    *,
    enabled: bool | None = None,
    rate: Decimal | None = None,
    qty: Decimal | None = None,
    mark_manual: bool | None = True,
) -> dict[str, Any]:
    """Patch one line, recompute ext + summary totals."""
    from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary

    row = db.scalars(
        select(EstimateLaborLine).where(
            EstimateLaborLine.section_id == section_id,
            EstimateLaborLine.code == code,
        )
    ).first()
    if not row:
        # ensure base set exists
        get_or_refresh_labor(db, section_id)
        row = db.scalars(
            select(EstimateLaborLine).where(
                EstimateLaborLine.section_id == section_id,
                EstimateLaborLine.code == code,
            )
        ).first()
    if not row:
        raise ValueError(f"labor line {code} not found")

    if enabled is not None:
        row.enabled = enabled
    if rate is not None:
        row.rate = _d(rate)
    if qty is not None:
        row.qty = _d(qty)

    # mark_manual is a three-state flag. True pins the line so a recalc leaves it
    # alone; False explicitly hands it back to the company default, which is the
    # only way to undo an override (before this, once manual was always manual);
    # None leaves the flag as it is, for an enabled-only toggle.
    if mark_manual is True and (rate is not None or qty is not None):
        row.is_manual = True
    elif mark_manual is False:
        row.is_manual = False

    row.ext_cost = (
        (_d(row.qty) * _d(row.rate)).quantize(Decimal("0.01")) if row.enabled else Decimal("0.00")
    )
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    all_rows = list(
        db.scalars(
            select(EstimateLaborLine).where(EstimateLaborLine.section_id == section_id)
        ).all()
    )
    labor_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "labor"), Decimal("0")
    ).quantize(Decimal("0.01"))
    super_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "supervision"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (labor_cost + super_cost).quantize(Decimal("0.01"))

    summary = db.get(EstimateLaborSummary, section_id)
    if summary:
        summary.total_labor_cost = labor_cost
        summary.total_supervision_cost = super_cost
        summary.total_cost = total
        summary.cost_per_sf = (
            (total / summary.total_sf).quantize(Decimal("0.0001"))
            if summary.total_sf and summary.total_sf > 0
            else None
        )
        # The equipment ladder rides super_days off this summary. On piers the
        # days are TYPED — there is no area to derive them from — so editing
        # the superintendent line has to move the summary with it, or the
        # rental days stay at whatever they were and nothing says why.
        if code == "superintendent":
            summary.super_days = _d(row.qty)
            days_per_week = _rate_numeric(
                db, section_kind(db, section_id), "labor_super_days_per_week", Decimal("7")
            )
            summary.super_weeks = (
                (_d(row.qty) / days_per_week).quantize(Decimal("0.0001"))
                if days_per_week > 0
                else Decimal("0")
            )
        summary.refreshed_at = datetime.now(timezone.utc)

    # A supervision change moves the equipment ladder, so the equipment
    # takeoff has to be rewritten before the costs are re-added — but only if
    # it already exists. Opening a section is what creates one.
    if code == "superintendent":
        from app.models.estimate_equipment import EstimateEquipmentSummary
        from app.services.estimate_equipment import refresh_and_store_equipment

        if db.get(EstimateEquipmentSummary, section_id) is not None:
            refresh_and_store_equipment(db, section_id)

    from app.services.costing import refresh_pour_costs_for_id
    refresh_pour_costs_for_id(db, section_id)
    db.commit()
    return load_stored_labor(db, section_id)  # type: ignore[return-value]
