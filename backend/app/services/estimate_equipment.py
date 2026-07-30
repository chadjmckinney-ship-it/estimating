"""
Equipment takeoff for mono-slab estimates (Excel 04 EQUIPMENT).

Days ladder (from superintendent days E91):
  bands add: ≤3 → d; else base 7; +7 if 5–10; +14 if 10–15; +23 if 15–20;
  +53 if 20–40; +83 if 40–60; …  (e.g. 27 days → 7+53 = 60)

Rental tier billing (Excel O15 style, no markup):
  1–3 days: days × rate
  4–7: 3 × rate
  8–20: (days/7) × 3 × rate
  21–29: 9 × rate
  30+: (days/30) × 9 × rate

Pumping: concrete CY × $/CY (catalog).
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


def equip_days_from_super(super_days: float | Decimal) -> Decimal:
    """Excel additive band ladder on superintendent days."""
    d = float(super_days or 0)
    if d <= 0:
        return Decimal("0")
    total = 0.0
    # IF(E>0, IF(E<=3, E, 7), 0)
    total += d if d <= 3 else 7
    if 5 < d <= 10:
        total += 7
    if 10 < d <= 15:
        total += 14
    if 15 < d <= 20:
        total += 23
    if 20 < d <= 40:
        total += 53
    if 40 < d <= 60:
        total += 83
    if 60 < d <= 80:
        total += 113
    if 80 < d <= 100:
        total += 143
    if 100 < d <= 120:
        total += 163
    if d > 120:
        # extend roughly: +20 per 20 days past 120
        total += 163 + ((d - 120) // 20) * 20
    return Decimal(str(total)).quantize(Decimal("0.0001"))


def rental_billable_units(days: float | Decimal, use_tiers: bool = True) -> Decimal:
    """
    Convert calendar days to billable day-equivalents (Excel tier).
    Returns units such that cost = units × day_rate.
    """
    d = float(days or 0)
    if d <= 0:
        return Decimal("0")
    if not use_tiers:
        return Decimal(str(d)).quantize(Decimal("0.0001"))
    if d < 4:
        units = d
    elif d < 8:
        units = 3.0
    elif d < 21:
        units = (d / 7.0) * 3.0
    elif d < 30:
        units = 9.0
    else:
        units = (d / 30.0) * 9.0
    return Decimal(str(units)).quantize(Decimal("0.0001"))


def _super_days(db: Session, estimate_id: UUID) -> Decimal:
    # Prefer labor summary if present
    row = db.execute(
        text(
            """
            SELECT super_days FROM estimate_labor_summary
            WHERE estimate_id = :eid
            """
        ),
        {"eid": str(estimate_id)},
    ).scalar()
    if row is not None:
        return _d(row)
    # Fallback: SF / 16000 * 7
    sf = db.execute(
        text(
            "SELECT coalesce(sum(square_footage),0) FROM mono_slabs WHERE estimate_id = :eid"
        ),
        {"eid": str(estimate_id)},
    ).scalar()
    sf_per_week = _setting_numeric(db, "labor_super_sf_per_week", Decimal("16000"))
    days_per_week = _setting_numeric(db, "labor_super_days_per_week", Decimal("7"))
    sf = _d(sf)
    if sf_per_week <= 0 or sf <= 0:
        return Decimal("0")
    return (sf / sf_per_week * days_per_week).quantize(Decimal("0.0001"))


def equipment_drivers(db: Session, estimate_id: UUID) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS pour_count,
              coalesce(sum(square_footage), 0) AS total_sf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy
            FROM mono_slabs
            WHERE estimate_id = :eid
            """
        ),
        {"eid": str(estimate_id)},
    ).mappings().one()
    super_days = _super_days(db, estimate_id)
    equip_days = equip_days_from_super(super_days)
    return {
        "pour_count": int(row["pour_count"] or 0),
        "total_sf": _d(row["total_sf"]),
        "super_days": super_days,
        "equip_days": equip_days,
        "total_concrete_cy": _d(row["total_concrete_cy"]),
    }


def _find_equip(db: Session, *parts: str) -> dict[str, Any] | None:
    clauses = " AND ".join(f"name ILIKE :p{i}" for i in range(len(parts)))
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(parts)}
    row = db.execute(
        text(
            f"""
            SELECT id, code, name, unit, unit_cost
            FROM equipment
            WHERE is_active AND {clauses}
            ORDER BY sort_order, id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    return dict(row) if row else None


def calc_estimate_equipment(db: Session, estimate_id: UUID) -> dict[str, Any]:
    d = equipment_drivers(db, estimate_id)
    days = float(d["equip_days"])
    cy = float(d["total_concrete_cy"])
    use_tiers = str(
        _setting_numeric(db, "equip_use_rental_tiers", Decimal("1"))
    ) not in ("0", "0.0")
    # system_settings stores jsonb true as not numeric - handle both
    tier_raw = db.execute(
        text("SELECT value #>> '{}' FROM system_settings WHERE key = 'equip_use_rental_tiers'")
    ).scalar()
    if tier_raw is not None:
        use_tiers = str(tier_raw).strip().lower() not in ("false", "0", "no")

    vault_rate = float(_setting_numeric(db, "equip_vault_day_rate", Decimal("25")))
    misc_rate = float(_setting_numeric(db, "equip_misc_day_rate", Decimal("55")))

    def day_line(
        *,
        code: str,
        label: str,
        rate: float,
        equipment_id: int | None,
        order: int,
        enabled: bool = True,
        notes: str | None = None,
        default_days: float | None = None,
    ) -> dict[str, Any]:
        dq = default_days if default_days is not None else days
        bill = rental_billable_units(dq, use_tiers=use_tiers)
        rt = _d(rate)
        ext = (bill * rt).quantize(Decimal("0.01")) if enabled else Decimal("0.00")
        return {
            "group_name": "equipment",
            "code": code,
            "label": label,
            "enabled": enabled,
            "equipment_id": equipment_id,
            "days_qty": _d(dq).quantize(Decimal("0.0001")),
            "rate": rt.quantize(Decimal("0.0001")),
            "unit": "DAY",
            "billable_units": bill,
            "ext_cost": ext,
            "formula": (
                f"days from super ladder ({d['equip_days']}); "
                f"billable={bill} × rate"
                + (" (rental tiers)" if use_tiers else " (days×rate)")
            ),
            "notes": notes,
            "sort_order": order,
            "is_manual": False,
        }

    sky = _find_equip(db, "SkyTrack") or _find_equip(db, "SKY")
    mini = _find_equip(db, "MINI EXCAVATOR") or _find_equip(db, "MINI")
    trench = _find_equip(db, "TRENCHER")
    skid = _find_equip(db, "SKID STEER") or _find_equip(db, "SKID")
    pump = _find_equip(db, "Pump") or _find_equip(db, "PUMP")

    lines: list[dict[str, Any]] = [
        day_line(
            code="skytrack",
            label="SKY TRACK",
            rate=float(sky["unit_cost"]) if sky and sky.get("unit_cost") else 425,
            equipment_id=sky["id"] if sky else None,
            order=10,
            enabled=False,  # often 0 on SOG
            notes="Off by default — enable when used",
            default_days=0,
        ),
        day_line(
            code="mini_excavator",
            label="MINI EXCAVATOR",
            rate=float(mini["unit_cost"]) if mini and mini.get("unit_cost") else 475,
            equipment_id=mini["id"] if mini else None,
            order=20,
        ),
        day_line(
            code="trencher",
            label="TRENCHER",
            rate=float(trench["unit_cost"]) if trench and trench.get("unit_cost") else 325,
            equipment_id=trench["id"] if trench else None,
            order=30,
        ),
        day_line(
            code="skid_steer",
            label="SKID STEER",
            rate=float(skid["unit_cost"]) if skid and skid.get("unit_cost") else 325,
            equipment_id=skid["id"] if skid else None,
            order=40,
        ),
        day_line(
            code="vault",
            label="VAULT",
            rate=vault_rate,
            equipment_id=None,
            order=50,
        ),
        day_line(
            code="misc_equip",
            label="MISCELLANEOUS",
            rate=misc_rate,
            equipment_id=None,
            order=60,
        ),
    ]

    # Contract / related
    pump_rate = float(pump["unit_cost"]) if pump and pump.get("unit_cost") else 16
    pump_ext = (_d(cy) * _d(pump_rate)).quantize(Decimal("0.01")) if cy > 0 else Decimal("0")
    lines.append(
        {
            "group_name": "contract",
            "code": "concrete_pump",
            "label": "CONCRETE PUMPING",
            "enabled": True,
            "equipment_id": pump["id"] if pump else None,
            "days_qty": _d(cy).quantize(Decimal("0.0001")),
            "rate": _d(pump_rate).quantize(Decimal("0.0001")),
            "unit": "CY",
            "billable_units": _d(cy).quantize(Decimal("0.0001")),
            "ext_cost": pump_ext,
            "formula": "total_concrete_cy × $/CY",
            "notes": None,
            "sort_order": 100,
            "is_manual": False,
        }
    )
    lines.append(
        {
            "group_name": "contract",
            "code": "haul_off",
            "label": "HAUL OFF",
            "enabled": True,
            "equipment_id": None,
            "days_qty": Decimal("0"),
            "rate": Decimal("12.5000"),
            "unit": "CY",
            "billable_units": Decimal("0"),
            "ext_cost": Decimal("0.00"),
            "formula": "dirt CY (manual / later)",
            "notes": "Qty starts at 0",
            "sort_order": 110,
            "is_manual": False,
        }
    )
    lines.append(
        {
            "group_name": "contract",
            "code": "engineering",
            "label": "ENGINEERING",
            "enabled": False,
            "equipment_id": None,
            "days_qty": d["total_sf"],
            "rate": Decimal("0.2000"),
            "unit": "/SF",
            "billable_units": d["total_sf"],
            "ext_cost": Decimal("0.00"),
            "formula": "total_sf × rate (off by default)",
            "notes": None,
            "sort_order": 120,
            "is_manual": False,
        }
    )

    equip_cost = sum(
        (_d(ln["ext_cost"]) for ln in lines if ln["group_name"] == "equipment"),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    contract_cost = sum(
        (_d(ln["ext_cost"]) for ln in lines if ln["group_name"] == "contract"),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    total = (equip_cost + contract_cost).quantize(Decimal("0.01"))
    cpsf = (total / d["total_sf"]).quantize(Decimal("0.0001")) if d["total_sf"] > 0 else None

    return {
        "drivers": d,
        "lines": lines,
        "total_equipment_cost": equip_cost,
        "total_contract_cost": contract_cost,
        "total_cost": total,
        "cost_per_sf": cpsf,
        "use_rental_tiers": use_tiers,
        "stored": False,
        "refreshed_at": None,
    }


def refresh_and_store_equipment(db: Session, estimate_id: UUID) -> dict[str, Any]:
    from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary

    data = calc_estimate_equipment(db, estimate_id)
    drivers = data["drivers"]
    lines = data["lines"]

    existing = {
        r.code: r
        for r in db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.estimate_id == estimate_id
            )
        ).all()
    }
    manuals = {c: r for c, r in existing.items() if r.is_manual}

    db.execute(
        delete(EstimateEquipmentLine).where(
            EstimateEquipmentLine.estimate_id == estimate_id,
            EstimateEquipmentLine.is_manual.is_(False),
        )
    )
    db.flush()
    now = datetime.now(timezone.utc)
    use_tiers = data.get("use_rental_tiers", True)

    for ln in lines:
        if ln["code"] in manuals:
            m = manuals[ln["code"]]
            m.formula = ln.get("formula")
            m.label = ln.get("label") or m.label
            m.unit = ln.get("unit") or m.unit
            m.group_name = ln["group_name"]
            m.sort_order = ln["sort_order"]
            m.equipment_id = ln.get("equipment_id")
            # recompute cost from stored days/rate
            if m.unit == "DAY":
                m.billable_units = rental_billable_units(m.days_qty, use_tiers=use_tiers)
            else:
                m.billable_units = _d(m.days_qty)
            m.ext_cost = (
                (_d(m.billable_units) * _d(m.rate)).quantize(Decimal("0.01"))
                if m.enabled
                else Decimal("0.00")
            )
            m.updated_at = now
            continue

        prev = existing.get(ln["code"])
        enabled = prev.enabled if prev is not None else ln["enabled"]
        rate = prev.rate if prev is not None else ln["rate"]
        days_qty = ln["days_qty"]
        # preserve user day qty if they set without is_manual and skytrack-style zeros
        if prev is not None and prev.code in ("skytrack",) and prev.days_qty is not None:
            # keep previous skytrack days if they enabled and set
            if prev.enabled and prev.days_qty > 0:
                days_qty = prev.days_qty

        if ln["unit"] == "DAY":
            bill = rental_billable_units(days_qty, use_tiers=use_tiers)
        else:
            bill = _d(days_qty)
        ext = (_d(bill) * _d(rate)).quantize(Decimal("0.01")) if enabled else Decimal("0.00")

        db.add(
            EstimateEquipmentLine(
                estimate_id=estimate_id,
                group_name=ln["group_name"],
                code=ln["code"],
                label=ln["label"],
                enabled=enabled,
                equipment_id=ln.get("equipment_id"),
                days_qty=_d(days_qty),
                rate=_d(rate),
                unit=ln["unit"],
                billable_units=_d(bill),
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
            select(EstimateEquipmentLine)
            .where(EstimateEquipmentLine.estimate_id == estimate_id)
            .order_by(EstimateEquipmentLine.sort_order)
        ).all()
    )
    equip_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "equipment"), Decimal("0")
    ).quantize(Decimal("0.01"))
    contract_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "contract"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (equip_cost + contract_cost).quantize(Decimal("0.01"))
    cpsf = (
        (total / drivers["total_sf"]).quantize(Decimal("0.0001"))
        if drivers["total_sf"] > 0
        else None
    )

    summary = db.get(EstimateEquipmentSummary, estimate_id)
    if summary is None:
        summary = EstimateEquipmentSummary(estimate_id=estimate_id)
        db.add(summary)
    summary.pour_count = drivers["pour_count"]
    summary.total_sf = drivers["total_sf"]
    summary.super_days = drivers["super_days"]
    summary.equip_days = drivers["equip_days"]
    summary.total_concrete_cy = drivers["total_concrete_cy"]
    summary.total_equipment_cost = equip_cost
    summary.total_contract_cost = contract_cost
    summary.total_cost = total
    summary.cost_per_sf = cpsf
    summary.refreshed_at = now
    db.commit()
    return load_stored_equipment(db, estimate_id)


def load_stored_equipment(db: Session, estimate_id: UUID) -> dict[str, Any] | None:
    from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary

    summary = db.get(EstimateEquipmentSummary, estimate_id)
    if summary is None:
        return None
    rows = list(
        db.scalars(
            select(EstimateEquipmentLine)
            .where(EstimateEquipmentLine.estimate_id == estimate_id)
            .order_by(EstimateEquipmentLine.sort_order, EstimateEquipmentLine.code)
        ).all()
    )
    lines = [
        {
            "id": str(r.id),
            "group_name": r.group_name,
            "code": r.code,
            "label": r.label,
            "enabled": r.enabled,
            "equipment_id": r.equipment_id,
            "days_qty": r.days_qty,
            "rate": r.rate,
            "unit": r.unit,
            "billable_units": r.billable_units,
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
            "super_days": summary.super_days,
            "equip_days": summary.equip_days,
            "total_concrete_cy": summary.total_concrete_cy,
        },
        "lines": lines,
        "total_equipment_cost": summary.total_equipment_cost,
        "total_contract_cost": summary.total_contract_cost,
        "total_cost": summary.total_cost,
        "cost_per_sf": summary.cost_per_sf,
        "stored": True,
        "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
    }


def get_or_refresh_equipment(db: Session, estimate_id: UUID) -> dict[str, Any]:
    stored = load_stored_equipment(db, estimate_id)
    if stored is not None:
        return stored
    return refresh_and_store_equipment(db, estimate_id)


def update_equipment_line(
    db: Session,
    estimate_id: UUID,
    code: str,
    *,
    enabled: bool | None = None,
    rate: Decimal | None = None,
    days_qty: Decimal | None = None,
    mark_manual: bool = False,
) -> dict[str, Any]:
    from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary

    row = db.scalars(
        select(EstimateEquipmentLine).where(
            EstimateEquipmentLine.estimate_id == estimate_id,
            EstimateEquipmentLine.code == code,
        )
    ).first()
    if not row:
        get_or_refresh_equipment(db, estimate_id)
        row = db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.estimate_id == estimate_id,
                EstimateEquipmentLine.code == code,
            )
        ).first()
    if not row:
        raise ValueError(f"equipment line {code} not found")

    if enabled is not None:
        row.enabled = enabled
    if rate is not None:
        row.rate = _d(rate)
        if mark_manual:
            row.is_manual = True
    if days_qty is not None:
        row.days_qty = _d(days_qty)
        if mark_manual:
            row.is_manual = True

    tier_raw = db.execute(
        text("SELECT value #>> '{}' FROM system_settings WHERE key = 'equip_use_rental_tiers'")
    ).scalar()
    use_tiers = True
    if tier_raw is not None:
        use_tiers = str(tier_raw).strip().lower() not in ("false", "0", "no")

    if row.unit == "DAY":
        row.billable_units = rental_billable_units(row.days_qty, use_tiers=use_tiers)
    else:
        row.billable_units = _d(row.days_qty)
    row.ext_cost = (
        (_d(row.billable_units) * _d(row.rate)).quantize(Decimal("0.01"))
        if row.enabled
        else Decimal("0.00")
    )
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    all_rows = list(
        db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.estimate_id == estimate_id
            )
        ).all()
    )
    equip_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "equipment"), Decimal("0")
    ).quantize(Decimal("0.01"))
    contract_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "contract"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (equip_cost + contract_cost).quantize(Decimal("0.01"))

    summary = db.get(EstimateEquipmentSummary, estimate_id)
    if summary:
        summary.total_equipment_cost = equip_cost
        summary.total_contract_cost = contract_cost
        summary.total_cost = total
        summary.cost_per_sf = (
            (total / summary.total_sf).quantize(Decimal("0.0001"))
            if summary.total_sf and summary.total_sf > 0
            else None
        )
        summary.refreshed_at = datetime.now(timezone.utc)
    db.commit()
    return load_stored_equipment(db, estimate_id)  # type: ignore[return-value]
