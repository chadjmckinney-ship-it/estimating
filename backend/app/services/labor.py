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

from app.services.calc import _setting_numeric


def _d(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def labor_drivers(db: Session, estimate_id: UUID) -> dict[str, Any]:
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
                  WHERE dm.estimate_id = :eid AND gb.kind = 'drop'
              ), 0) AS drops_ff,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_slab_concrete_cy), 0) AS total_slab_cy
            FROM mono_slabs
            WHERE estimate_id = :eid
            """
        ),
        {"eid": str(estimate_id)},
    ).mappings().one()

    sf = _d(row["total_sf"])
    rebar = _d(row["total_rebar_lb"])
    tons = (rebar / Decimal("2000")).quantize(Decimal("0.0001")) if rebar else Decimal("0")

    sf_per_week = _setting_numeric(db, "labor_super_sf_per_week", Decimal("16000"))
    days_per_week = _setting_numeric(db, "labor_super_days_per_week", Decimal("7"))
    weeks = (sf / sf_per_week).quantize(Decimal("0.0001")) if sf_per_week > 0 and sf > 0 else Decimal("0")
    days = (weeks * days_per_week).quantize(Decimal("0.0001"))

    return {
        "pour_count": int(row["pour_count"] or 0),
        "total_sf": sf,
        "drops_ff": _d(row["drops_ff"]),
        "total_rebar_lb": rebar,
        "total_rebar_tons": tons,
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "total_slab_cy": _d(row["total_slab_cy"]),
        "super_weeks": weeks,
        "super_days": days,
        "sf_per_week": sf_per_week,
        "days_per_week": days_per_week,
    }


def _rate(db: Session, key: str, default: Decimal) -> Decimal:
    return _setting_numeric(db, key, default)


def calc_labor_materials(db: Session, estimate_id: UUID) -> dict[str, Any]:
    """Build labor + supervision line dicts (not yet stored)."""
    d = labor_drivers(db, estimate_id)
    sf = float(d["total_sf"])
    drops = float(d["drops_ff"])
    tons = float(d["total_rebar_tons"])
    days = float(d["super_days"])
    weeks = float(d["super_weeks"])

    r_form = float(_rate(db, "labor_forming_sf", Decimal("0.45")))
    r_grade = float(_rate(db, "labor_grading_sf", Decimal("0.70")))
    r_place = float(_rate(db, "labor_place_finish_sf", Decimal("0.55")))
    r_wreck = float(_rate(db, "labor_wreck_sf", Decimal("0.20")))
    r_drops = float(_rate(db, "labor_drops_ff", Decimal("8")))
    r_exc = float(_rate(db, "labor_excavation_cy", Decimal("12")))
    r_hd = float(_rate(db, "labor_hold_down_ea", Decimal("100")))
    r_tie = float(_rate(db, "labor_tie_steel_ton", Decimal("450")))
    r_super = float(_rate(db, "labor_super_day_rate", Decimal("425")))
    r_fore = float(_rate(db, "labor_foreman_day_rate", Decimal("250")))
    r_exp = float(_rate(db, "labor_expense_day_rate", Decimal("100")))
    r_pm = float(_rate(db, "labor_pm_day_rate", Decimal("200")))

    def line(
        *,
        group: str,
        code: str,
        label: str,
        rate: float,
        unit: str,
        qty: float,
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

    lines: list[dict[str, Any]] = [
        line(
            group="labor",
            code="forming",
            label="FORMING",
            rate=r_form,
            unit="/SF",
            qty=sf,
            formula="total_sf × rate",
            order=10,
        ),
        line(
            group="labor",
            code="grading",
            label="GRADING / CABLES",
            rate=r_grade,
            unit="/SF",
            qty=sf,
            formula="total_sf × rate",
            order=20,
        ),
        line(
            group="labor",
            code="place_finish",
            label="PLACE AND FINISH",
            rate=r_place,
            unit="/SF",
            qty=sf,
            formula="total_sf × rate",
            order=30,
        ),
        line(
            group="labor",
            code="wreck",
            label="WRECK AND CLEAN UP",
            rate=r_wreck,
            unit="/SF",
            qty=sf,
            formula="total_sf × rate",
            order=40,
        ),
        line(
            group="labor",
            code="drops",
            label="DROPS",
            rate=r_drops,
            unit="/FF",
            qty=drops,
            formula="drops_ff × rate",
            order=50,
        ),
        line(
            group="labor",
            code="labor_add",
            label="LABOR ADD",
            rate=0,
            unit="LS",
            qty=0,
            formula="manual / pour labor adds (later)",
            notes="Enter total $ or leave 0",
            order=60,
        ),
        line(
            group="labor",
            code="excavation",
            label="EXCAVATION ADD",
            rate=r_exc,
            unit="/CY",
            qty=0,
            formula="dirt CY (manual / later from dirt calc)",
            notes="Qty starts at 0 until dirt takeoff",
            order=70,
        ),
        line(
            group="labor",
            code="hold_downs",
            label="HOLD DOWNS / FTGS",
            rate=r_hd,
            unit="/EA",
            qty=0,
            formula="hold-down count (manual / pour field later)",
            order=80,
        ),
        line(
            group="labor",
            code="tie_steel",
            label="TIE STEEL",
            rate=r_tie,
            unit="/TON",
            qty=tons,
            formula="(total_rebar_lb / 2000) × rate",
            order=90,
        ),
        line(
            group="labor",
            code="extra_hours",
            label="EXTRA HOURS",
            rate=0,
            unit="LS",
            qty=0,
            formula="manual lump sum",
            order=100,
        ),
        # Supervision
        line(
            group="supervision",
            code="superintendent",
            label="SUPERINTENDENT",
            rate=r_super,
            unit="/DAY",
            qty=days,
            formula=f"SF / {d['sf_per_week']} weeks × {d['days_per_week']} days × rate",
            notes=f"{weeks:.4f} weeks",
            order=200,
        ),
        line(
            group="supervision",
            code="foreman",
            label="FOREMAN",
            rate=r_fore,
            unit="/DAY",
            qty=0,  # Excel often leaves blank until assigned
            formula="days × rate (set qty = super days when used)",
            notes="Default qty 0 — set equal to super days if needed",
            order=210,
        ),
        line(
            group="supervision",
            code="expense",
            label="EXPENSE ALLOWANCE",
            rate=r_exp,
            unit="/DAY",
            qty=days,
            formula="super days × rate",
            order=220,
        ),
        line(
            group="supervision",
            code="pm",
            label="PROJECT MANAGEMENT",
            rate=r_pm,
            unit="/DAY",
            qty=days,
            formula="super days × rate",
            order=230,
        ),
    ]

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


def refresh_and_store_labor(db: Session, estimate_id: UUID) -> dict[str, Any]:
    from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary

    data = calc_labor_materials(db, estimate_id)
    drivers = data["drivers"]
    lines = data["lines"]

    existing = {
        r.code: r
        for r in db.scalars(
            select(EstimateLaborLine).where(EstimateLaborLine.estimate_id == estimate_id)
        ).all()
    }
    manuals = {c: r for c, r in existing.items() if r.is_manual}

    db.execute(
        delete(EstimateLaborLine).where(
            EstimateLaborLine.estimate_id == estimate_id,
            EstimateLaborLine.is_manual.is_(False),
        )
    )
    db.flush()

    now = datetime.now(timezone.utc)
    for ln in lines:
        if ln["code"] in manuals:
            m = manuals[ln["code"]]
            # keep rate/qty/enabled for manual; refresh formula label
            m.formula = ln.get("formula")
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
                estimate_id=estimate_id,
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
            .where(EstimateLaborLine.estimate_id == estimate_id)
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

    summary = db.get(EstimateLaborSummary, estimate_id)
    if summary is None:
        summary = EstimateLaborSummary(estimate_id=estimate_id)
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

    db.commit()
    return load_stored_labor(db, estimate_id)


def load_stored_labor(db: Session, estimate_id: UUID) -> dict[str, Any] | None:
    from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary

    summary = db.get(EstimateLaborSummary, estimate_id)
    if summary is None:
        return None

    rows = list(
        db.scalars(
            select(EstimateLaborLine)
            .where(EstimateLaborLine.estimate_id == estimate_id)
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
    return {
        "drivers": {
            "pour_count": summary.pour_count,
            "total_sf": summary.total_sf,
            "drops_ff": summary.drops_ff,
            "total_rebar_lb": summary.total_rebar_lb,
            "total_rebar_tons": summary.total_rebar_tons,
            "super_weeks": summary.super_weeks,
            "super_days": summary.super_days,
        },
        "lines": lines,
        "total_labor_cost": summary.total_labor_cost,
        "total_supervision_cost": summary.total_supervision_cost,
        "total_cost": summary.total_cost,
        "cost_per_sf": summary.cost_per_sf,
        "stored": True,
        "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
    }


def get_or_refresh_labor(db: Session, estimate_id: UUID) -> dict[str, Any]:
    stored = load_stored_labor(db, estimate_id)
    if stored is not None:
        return stored
    return refresh_and_store_labor(db, estimate_id)


def update_labor_line(
    db: Session,
    estimate_id: UUID,
    code: str,
    *,
    enabled: bool | None = None,
    rate: Decimal | None = None,
    qty: Decimal | None = None,
    mark_manual: bool = False,
) -> dict[str, Any]:
    """Patch one line, recompute ext + summary totals."""
    from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary

    row = db.scalars(
        select(EstimateLaborLine).where(
            EstimateLaborLine.estimate_id == estimate_id,
            EstimateLaborLine.code == code,
        )
    ).first()
    if not row:
        # ensure base set exists
        get_or_refresh_labor(db, estimate_id)
        row = db.scalars(
            select(EstimateLaborLine).where(
                EstimateLaborLine.estimate_id == estimate_id,
                EstimateLaborLine.code == code,
            )
        ).first()
    if not row:
        raise ValueError(f"labor line {code} not found")

    if enabled is not None:
        row.enabled = enabled
    if rate is not None:
        row.rate = _d(rate)
        if mark_manual:
            row.is_manual = True
    if qty is not None:
        row.qty = _d(qty)
        if mark_manual:
            row.is_manual = True

    row.ext_cost = (
        (_d(row.qty) * _d(row.rate)).quantize(Decimal("0.01")) if row.enabled else Decimal("0.00")
    )
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    all_rows = list(
        db.scalars(
            select(EstimateLaborLine).where(EstimateLaborLine.estimate_id == estimate_id)
        ).all()
    )
    labor_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "labor"), Decimal("0")
    ).quantize(Decimal("0.01"))
    super_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "supervision"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (labor_cost + super_cost).quantize(Decimal("0.01"))

    summary = db.get(EstimateLaborSummary, estimate_id)
    if summary:
        summary.total_labor_cost = labor_cost
        summary.total_supervision_cost = super_cost
        summary.total_cost = total
        summary.cost_per_sf = (
            (total / summary.total_sf).quantize(Decimal("0.0001"))
            if summary.total_sf and summary.total_sf > 0
            else None
        )
        summary.refreshed_at = datetime.now(timezone.utc)

    db.commit()
    return load_stored_labor(db, estimate_id)  # type: ignore[return-value]
