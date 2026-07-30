"""
Forming / lumber material quantities for mono-slab estimates.

Rules from Excel 04-PT Slab on Grade → LUMBER AND ACCESS (ACC #02).
Drivers roll up from mono pours (+ optional grade-beam related later).

Formulas (form_pct = system form_percent, default 0.50):

  2x6 LF        = perimeter_lf × form_pct
  2x4 LF        = (2x6_LF × 3 + drops_ff) × form_pct
  2x10 LF       = perimeter_lf × form_pct × 2
  2x4 bracing   = 3 × drops_ff
                  (Excel SUM(drop type + drop LF)×3 — type codes ignored; use drops FF only)
  siding sheets = ceil(perimeter_lf × 0.03 / 16)
  forming ply   = drops_ff / 32 × form_pct × 1.1
  stakes bndls  = round(2x10_LF / 25)
  16p nails box = ceil(perimeter_lf × 1.25 / 500)
  8p duplex box = ceil(perimeter_lf × 1.25 / 500)
  20p nails box = ceil(perimeter_lf × 1.25 / 500)  → catalog 16p if no 20p
  anchor bolts  = perimeter_lf / 150
  keyway / chamfer / redwood — manual (0 unless override)
  slab chairs   = ceil(total_sf / 15000)
  tie wire      = total_sf / 15000
  accessories   = steel_lb + mesh_sf × 0.75   (Excel L70 + L71×0.75)
  slab cure     = ceil(total_sf / 300 / 55)
  form release  — manual 0 for SOG usually

Carton forms / vapor rolls live elsewhere (poly SF, carton Y/N later).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.calc import _setting_numeric


def _ceil(x: float) -> int:
    return int(math.ceil(x - 1e-12)) if x > 0 else 0


def _round0(x: float) -> int:
    return int(round(x)) if x > 0 else 0


def _d(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def estimate_forming_drivers(db: Session, estimate_id: UUID) -> dict[str, Any]:
    """Roll up pour-level drivers used by forming formulas."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS pour_count,
              coalesce(sum(square_footage), 0) AS total_sf,
              coalesce(sum(perimeter_edge_lf), 0) AS perimeter_lf,
              coalesce(sum(drops_ff), 0) AS drops_ff,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_support_rebar_lb), 0) AS support_rebar_lb,
              coalesce(sum(CASE WHEN wire_mesh THEN square_footage ELSE 0 END), 0)
                AS mesh_sf
            FROM mono_slabs
            WHERE estimate_id = :eid
            """
        ),
        {"eid": str(estimate_id)},
    ).mappings().one()

    sys_form = _setting_numeric(db, "form_percent", Decimal("0.50"))
    form_waste = _setting_numeric(db, "form_waste", Decimal("0"))

    # Per-estimate override (Excel W65); NULL → system default
    est_row = db.execute(
        text("SELECT form_percent FROM estimates WHERE id = :eid"),
        {"eid": str(estimate_id)},
    ).mappings().first()
    est_form = est_row["form_percent"] if est_row else None
    form_pct = _d(est_form) if est_form is not None else sys_form

    return {
        "estimate_id": estimate_id,
        "pour_count": int(row["pour_count"] or 0),
        "total_sf": _d(row["total_sf"]),
        "perimeter_lf": _d(row["perimeter_lf"]),
        "drops_ff": _d(row["drops_ff"]),
        "total_rebar_lb": _d(row["total_rebar_lb"]),
        "support_rebar_lb": _d(row["support_rebar_lb"]),
        "mesh_sf": _d(row["mesh_sf"]),
        "form_percent": form_pct,
        "form_percent_is_override": est_form is not None,
        "form_percent_system_default": sys_form,
        "form_waste": form_waste,
    }


def _find_material(db: Session, *name_parts: str) -> dict[str, Any] | None:
    """Best-effort match on materials.name (case-insensitive contains all parts)."""
    clauses = " AND ".join(f"name ILIKE :p{i}" for i in range(len(name_parts)))
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(name_parts)}
    row = db.execute(
        text(
            f"""
            SELECT id, name, unit, unit_cost, category
            FROM materials
            WHERE coalesce(is_active, true) AND {clauses}
            ORDER BY sort_order NULLS LAST, id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    return dict(row) if row else None


def _line(
    *,
    code: str,
    label: str,
    qty: Decimal | float | int,
    unit: str,
    formula: str,
    material: dict[str, Any] | None,
    notes: str | None = None,
    form_waste: Decimal = Decimal("0"),
) -> dict[str, Any]:
    q = _d(qty).quantize(Decimal("0.001")) if not isinstance(qty, int) else Decimal(qty)
    if isinstance(qty, int):
        q = Decimal(qty)
    else:
        q = _d(qty).quantize(Decimal("0.001"))
    unit_cost = _d(material["unit_cost"]) if material and material.get("unit_cost") is not None else None
    ext = None
    if unit_cost is not None:
        ext = (q * unit_cost * (Decimal("1") + form_waste)).quantize(Decimal("0.01"))
    return {
        "code": code,
        "label": label,
        "qty": q,
        "unit": unit,
        "formula": formula,
        "notes": notes,
        "material_id": material["id"] if material else None,
        "material_name": material["name"] if material else None,
        "unit_cost": unit_cost,
        "ext_cost": ext,
        "group": "forming",
    }


def calc_forming_materials(db: Session, estimate_id: UUID) -> dict[str, Any]:
    """Return drivers + material lines for an estimate (mono slab forming package)."""
    d = estimate_forming_drivers(db, estimate_id)
    p = float(d["perimeter_lf"])
    drops = float(d["drops_ff"])
    sf = float(d["total_sf"])
    form_pct = float(d["form_percent"])
    waste = d["form_waste"]
    rebar = float(d["total_rebar_lb"])
    mesh = float(d["mesh_sf"])

    # --- Form lumber only (multiplied by form_percent) ---
    # 2x4, 2x6, 2x10, forming ply, masonite/siding
    qty_2x6 = p * form_pct
    qty_2x4 = (qty_2x6 * 3 + drops) * form_pct
    qty_2x10 = p * form_pct * 2
    qty_ply = (drops / 32.0) * form_pct * 1.1 if drops > 0 else 0.0
    qty_siding = _ceil(p * form_pct * 0.03 / 16.0) if p > 0 and form_pct > 0 else 0

    # --- Not scaled by form% (accessories / nails / bracing / stakes from Excel) ---
    qty_brace = 3.0 * drops
    # Stakes track 2x10 qty in Excel (so they follow form% indirectly)
    qty_stakes = _round0(qty_2x10 / 25.0) if qty_2x10 > 0 else 0
    qty_16p = _ceil(p * 1.25 / 500.0) if p > 0 else 0
    qty_8p = _ceil(p * 1.25 / 500.0) if p > 0 else 0
    qty_20p = _ceil(p * 1.25 / 500.0) if p > 0 else 0
    qty_anchors = p / 150.0 if p > 0 else 0.0
    qty_chairs = _ceil(sf / 15000.0) if sf > 0 else 0
    qty_tie = sf / 15000.0 if sf > 0 else 0.0
    qty_access = rebar + mesh * 0.75
    qty_cure = _ceil(sf / 300.0 / 55.0) if sf > 0 else 0

    m_2x4 = _find_material(db, "2 X 4")
    m_2x6 = _find_material(db, "2 X 6")
    m_2x10 = _find_material(db, "2 X 10")
    m_ply = _find_material(db, "FORMING PLY")
    m_siding = _find_material(db, "SIDING") or _find_material(db, "MASONITE")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_anchor = _find_material(db, "ANCHOR BOLTS 1/2") or _find_material(db, "ANCHOR BOLTS")
    m_keyway = _find_material(db, "KEYWAY")
    m_chamfer = _find_material(db, "CHAMFER")
    m_rw6 = _find_material(db, "1 X 6", "RED")
    m_rw8 = _find_material(db, "1 X 8", "RED")
    m_chairs = _find_material(db, "SLAB CHAIRS")
    m_tie = _find_material(db, "TIE WIRE")
    m_acc = _find_material(db, "ACCESSORIES")
    m_cure = _find_material(db, "SLAB CURE")
    m_release = _find_material(db, "FORM RELEASE")

    lines = [
        _line(
            code="2x6",
            label="2 X 6 X 16'",
            qty=qty_2x6,
            unit="LF",
            formula="perimeter_lf × form%",
            material=m_2x6,
            notes="Form lumber — uses form%",
            form_waste=waste,
        ),
        _line(
            code="2x4",
            label="2 X 4 X 16'",
            qty=qty_2x4,
            unit="LF",
            formula="(2x6_LF × 3 + drops_ff) × form%",
            material=m_2x4,
            notes="Form lumber — uses form%",
            form_waste=waste,
        ),
        _line(
            code="2x4_brace",
            label="2 x 4 BRACING",
            qty=qty_brace,
            unit="LF",
            formula="3 × drops_ff (not scaled by form%)",
            material=m_2x4,
            notes="Priced as 2x4; not multiplied by form%",
            form_waste=waste,
        ),
        _line(
            code="2x10",
            label="2 X 10 X 16'",
            qty=qty_2x10,
            unit="LF",
            formula="perimeter_lf × form% × 2",
            material=m_2x10,
            notes="Form lumber — uses form%",
            form_waste=waste,
        ),
        _line(
            code="siding",
            label='3/8" X 12" X 16\' SIDING (masonite)',
            qty=qty_siding,
            unit="SHEET",
            formula="ceil(perimeter_lf × form% × 0.03 / 16)",
            material=m_siding,
            notes="Form material — uses form%",
            form_waste=waste,
        ),
        _line(
            code="ply",
            label='3/4 " FORMING PLY',
            qty=qty_ply,
            unit="SHEET",
            formula="drops_ff / 32 × form% × 1.1",
            material=m_ply,
            notes="Form lumber — uses form%",
            form_waste=waste,
        ),
        _line(
            code="stakes",
            label="2 x 2 x 30 STAKES",
            qty=qty_stakes,
            unit="BUNDLE",
            formula="round(2x10_LF / 25) — follows 2x10 qty",
            material=m_stakes,
            notes="Derived from 2x10 (indirectly follows form%)",
            form_waste=waste,
        ),
        _line(
            code="16p",
            label="16p NAILS DUPLEX",
            qty=qty_16p,
            unit="BOX",
            formula="ceil(perimeter_lf × 1.25 / 500)",
            material=m_16p,
            form_waste=waste,
        ),
        _line(
            code="8p",
            label="8p DUPLEX",
            qty=qty_8p,
            unit="BOX",
            formula="ceil(perimeter_lf × 1.25 / 500)",
            material=m_8p,
            form_waste=waste,
        ),
        _line(
            code="20p",
            label="20p NAILS",
            qty=qty_20p,
            unit="BOX",
            formula="ceil(perimeter_lf × 1.25 / 500)",
            material=m_16p or m_6p,
            notes="No 20p in catalog — priced as 16p if available",
            form_waste=waste,
        ),
        _line(
            code="anchors",
            label="ANCHOR BOLTS",
            qty=qty_anchors,
            unit="BOX",
            formula="perimeter_lf / 150",
            material=m_anchor,
            form_waste=waste,
        ),
        _line(
            code="keyway",
            label="KEYWAY",
            qty=0,
            unit="LF",
            formula="manual (Excel often blank)",
            material=m_keyway,
            notes="Enter job keyway LF when known",
            form_waste=waste,
        ),
        _line(
            code="chamfer",
            label="CHAMFER",
            qty=0,
            unit="LF",
            formula="manual",
            material=m_chamfer,
            form_waste=waste,
        ),
        _line(
            code="rw6",
            label="1 X 6 RED WOOD",
            qty=0,
            unit="LF",
            formula="manual",
            material=m_rw6,
            form_waste=waste,
        ),
        _line(
            code="rw8",
            label="1 X 8 RED WOOD",
            qty=0,
            unit="LF",
            formula="manual",
            material=m_rw8,
            form_waste=waste,
        ),
        _line(
            code="chairs",
            label="SLAB CHAIRS",
            qty=qty_chairs,
            unit="BAG",
            formula="ceil(total_sf / 15000)",
            material=m_chairs,
            form_waste=waste,
        ),
        _line(
            code="tie_wire",
            label="TIE WIRE",
            qty=qty_tie,
            unit="ROLL",
            formula="total_sf / 15000",
            material=m_tie,
            form_waste=waste,
        ),
        _line(
            code="accessories",
            label="ACCESSORIES",
            qty=qty_access,
            unit="LB",
            formula="total_rebar_lb + mesh_sf × 0.75",
            material=m_acc,
            form_waste=waste,
        ),
        _line(
            code="cure",
            label="SLAB CURE",
            qty=qty_cure,
            unit="DRUM",
            formula="ceil(total_sf / 300 / 55)",
            material=m_cure,
            form_waste=waste,
        ),
        _line(
            code="form_release",
            label="FORM RELEASE",
            qty=0,
            unit="DRUM",
            formula="manual (usually 0 for SOG)",
            material=m_release,
            form_waste=waste,
        ),
    ]

    total_ext = sum((ln["ext_cost"] or Decimal("0")) for ln in lines)

    return {
        "drivers": {
            "pour_count": d["pour_count"],
            "total_sf": d["total_sf"],
            "perimeter_lf": d["perimeter_lf"],
            "drops_ff": d["drops_ff"],
            "mesh_sf": d["mesh_sf"],
            "total_rebar_lb": d["total_rebar_lb"],
            "form_percent": d["form_percent"],
            "form_percent_is_override": d.get("form_percent_is_override", False),
            "form_percent_system_default": d.get("form_percent_system_default"),
            "form_waste": d["form_waste"],
        },
        "lines": lines,
        "total_ext_cost": total_ext.quantize(Decimal("0.01")),
        "stored": False,
        "refreshed_at": None,
    }


def refresh_and_store_forming(db: Session, estimate_id: UUID) -> dict[str, Any]:
    """
    Recalculate forming takeoff from pours and persist to
    estimate_forming_lines + estimate_forming_summary.
    Keeps rows marked is_manual (qty/notes) for those codes.
    """
    from datetime import datetime, timezone

    from sqlalchemy import delete, select

    from app.models.estimate_forming import EstimateFormingLine, EstimateFormingSummary

    data = calc_forming_materials(db, estimate_id)
    drivers = data["drivers"]
    lines = data["lines"]

    # Preserve manual overrides
    existing = {
        r.code: r
        for r in db.scalars(
            select(EstimateFormingLine).where(
                EstimateFormingLine.estimate_id == estimate_id
            )
        ).all()
    }
    manuals = {c: r for c, r in existing.items() if r.is_manual}

    db.execute(
        delete(EstimateFormingLine).where(
            EstimateFormingLine.estimate_id == estimate_id,
            EstimateFormingLine.is_manual.is_(False),
        )
    )
    db.flush()

    now = datetime.now(timezone.utc)
    stored_lines: list[EstimateFormingLine] = []
    order = 0
    for ln in lines:
        order += 10
        if ln["code"] in manuals:
            # keep manual qty; still refresh cost if unit_cost changed
            m = manuals[ln["code"]]
            if ln.get("unit_cost") is not None:
                m.unit_cost = ln["unit_cost"]
                m.ext_cost = (
                    _d(m.qty) * _d(ln["unit_cost"]) * (Decimal("1") + _d(drivers["form_waste"]))
                ).quantize(Decimal("0.01"))
            m.material_id = ln.get("material_id")
            m.material_name = ln.get("material_name")
            m.formula = ln.get("formula")
            m.label = ln.get("label") or m.label
            m.unit = ln.get("unit") or m.unit
            m.sort_order = order
            m.updated_at = now
            stored_lines.append(m)
            continue

        row = EstimateFormingLine(
            estimate_id=estimate_id,
            code=ln["code"],
            label=ln["label"],
            qty=_d(ln["qty"]),
            unit=ln["unit"],
            formula=ln.get("formula"),
            notes=ln.get("notes"),
            material_id=ln.get("material_id"),
            material_name=ln.get("material_name"),
            unit_cost=ln.get("unit_cost"),
            ext_cost=ln.get("ext_cost"),
            sort_order=order,
            is_manual=False,
        )
        db.add(row)
        stored_lines.append(row)

    # Recompute total from all lines including manuals
    db.flush()
    all_rows = list(
        db.scalars(
            select(EstimateFormingLine)
            .where(EstimateFormingLine.estimate_id == estimate_id)
            .order_by(EstimateFormingLine.sort_order)
        ).all()
    )
    total_ext = sum((_d(r.ext_cost) for r in all_rows), Decimal("0")).quantize(
        Decimal("0.01")
    )

    summary = db.get(EstimateFormingSummary, estimate_id)
    if summary is None:
        summary = EstimateFormingSummary(estimate_id=estimate_id)
        db.add(summary)
    summary.pour_count = int(drivers["pour_count"])
    summary.total_sf = _d(drivers["total_sf"])
    summary.perimeter_lf = _d(drivers["perimeter_lf"])
    summary.drops_ff = _d(drivers["drops_ff"])
    summary.mesh_sf = _d(drivers["mesh_sf"])
    summary.total_rebar_lb = _d(drivers["total_rebar_lb"])
    summary.form_percent = _d(drivers["form_percent"])
    summary.form_waste = _d(drivers["form_waste"])
    summary.total_ext_cost = total_ext
    summary.refreshed_at = now

    db.commit()
    return load_stored_forming(db, estimate_id)


def set_form_percent_and_refresh(
    db: Session, estimate_id: UUID, form_percent: Decimal
) -> dict[str, Any]:
    """Save form% on the estimate (forms only) and rewrite forming lines."""
    from app.models.estimate import Estimate

    est = db.get(Estimate, estimate_id)
    if not est:
        raise ValueError("estimate not found")
    est.form_percent = _d(form_percent)
    db.flush()
    return refresh_and_store_forming(db, estimate_id)


def load_stored_forming(db: Session, estimate_id: UUID) -> dict[str, Any] | None:
    """Load persisted forming takeoff, or None if never refreshed."""
    from sqlalchemy import select

    from app.models.estimate_forming import EstimateFormingLine, EstimateFormingSummary

    summary = db.get(EstimateFormingSummary, estimate_id)
    if summary is None:
        return None

    rows = list(
        db.scalars(
            select(EstimateFormingLine)
            .where(EstimateFormingLine.estimate_id == estimate_id)
            .order_by(EstimateFormingLine.sort_order, EstimateFormingLine.code)
        ).all()
    )
    lines = [
        {
            "code": r.code,
            "label": r.label,
            "qty": r.qty,
            "unit": r.unit,
            "formula": r.formula or "",
            "notes": r.notes,
            "material_id": r.material_id,
            "material_name": r.material_name,
            "unit_cost": r.unit_cost,
            "ext_cost": r.ext_cost,
            "group": "forming",
            "is_manual": r.is_manual,
            "id": str(r.id),
        }
        for r in rows
    ]
    sys_form = _setting_numeric(db, "form_percent", Decimal("0.50"))
    est_row = db.execute(
        text("SELECT form_percent FROM estimates WHERE id = :eid"),
        {"eid": str(estimate_id)},
    ).mappings().first()
    est_form = est_row["form_percent"] if est_row else None

    return {
        "drivers": {
            "pour_count": summary.pour_count,
            "total_sf": summary.total_sf,
            "perimeter_lf": summary.perimeter_lf,
            "drops_ff": summary.drops_ff,
            "mesh_sf": summary.mesh_sf,
            "total_rebar_lb": summary.total_rebar_lb,
            "form_percent": summary.form_percent,
            "form_percent_is_override": est_form is not None,
            "form_percent_system_default": sys_form,
            "form_waste": summary.form_waste,
        },
        "lines": lines,
        "total_ext_cost": summary.total_ext_cost,
        "stored": True,
        "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
    }


def get_or_refresh_forming(db: Session, estimate_id: UUID) -> dict[str, Any]:
    """Return stored forming; if never saved, compute and store."""
    stored = load_stored_forming(db, estimate_id)
    if stored is not None:
        return stored
    return refresh_and_store_forming(db, estimate_id)
