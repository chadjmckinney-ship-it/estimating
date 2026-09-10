"""
The estimate Summary (sql/088): the workbook's Summary tab, read off the
priced job.

Chad, 2026-09-09: "there is something missing that the office uses from the
estimates.. a summary like that is in the excel spreadsheet.. pulls all the
materials form each section, supervision, everything thats in a project.. a
total of each the a breakdown per section.."

## What it reads

This module is a READER, the way material_costs.py is. Nothing is priced
here; every dollar is one the section was already costed at:

  * the purchases — concrete, rebar, PT, sand, poly, tape, mesh, weld
    plates, drilling — from `material_costs.section_material_costs`, which
    re-walks the stored takeoff at the rates the section was priced at;
  * the three stored line sets — forming materials, labor and supervision,
    equipment and contract services — at each enabled line's `ext_cost`, the
    same figure `costing._on_takeoff_lines` allocated onto the rows;
  * a miscellaneous item's typed allowances (forms, labor, supervision,
    equipment), which sit in its direct cost rather than on a line set;
  * the fuel & maintenance uplift on the rental days and the sales tax,
    both read back off the rows costing wrote them on.

Each line is filed under a cost code by `cost_code_lines`, and the code
says which JOB COST SUMMARY column it lands in. A labor line on a section
whose labor is in house takes its in-house code where the chart has one,
and lands in the LABOR column rather than SUB LABOR either way. A line the
table does not know is UNASSIGNED: counted in its own column so the section
still ties, and named so the office can file it from Settings.

## What it checks

A section's columns add to the section's stored cost. They do not always
add exactly: the purchase reader quantizes once per material where costing
quantized once per row (cents), and a section whose line sets were never
built has no forming, labor or equipment in the summary — nor in its cost,
since `_on_takeoff_lines` reads the same stored rows. The gap is reported
as `difference`, never smeared into a column.

## Margin Contingency and ESTIMATED PROFIT

The tab's 000091 Margin Contingency is the CONTINGENCY dollars only — its
G110 is the cost times Summary!P60, the contingency rate — and ESTIMATED
PROFIT is the price less every cost line and that contingency: the margin.
Here a section sells at cost × (1 + margin + contingency), so the
contingency's share of the markup is (sale − cost) × c ÷ (m + c) — which is
cost × c on every section but a miscellaneous one, whose sale is typed and
whose markup is whatever falls out (the misc tab's W column does the same
division). Profit is the rest of the markup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.cost_code import CATEGORY_LABELS, LINE_KINDS, CostCode, CostCodeLine
from app.models.estimate import Estimate
from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary
from app.models.estimate_forming import EstimateFormingLine, EstimateFormingSummary
from app.models.estimate_labor import EstimateLaborLine, EstimateLaborSummary
from app.models.estimate_section import MISC_KINDS, EstimateSection
from app.models.estimator import Estimator
from app.models.project import Project

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_ZERO = Decimal("0")

# The JOB COST SUMMARY's money columns, in the tab's order (G..U), then the
# two the app carries on their own: the sales tax costing keeps apart from
# the purchases (the tab folds it into them), and what nothing has filed.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("forms_accessories", "FORMS & ACCESSORIES"),
    ("grade_material", "GRADE MATERIAL"),
    ("poly_sealing", "POLY / SEALING"),
    ("pt_cables", "PT CABLES"),
    ("rebar", "REBAR"),
    ("rebar_accessories", "REBAR ACCESSORIES"),
    ("concrete", "CONCRETE"),
    ("seal_cure", "SEAL / WTR PRF / CURE"),
    ("other_subs", "OTHER SUBS"),
    ("sub_labor", "SUB LABOR"),
    ("labor", "LABOR"),
    ("supervision", "SUPV"),
    ("pm", "PM"),
    ("equipment", "EQUIP"),
    ("out_of_town", "OUT OF TOWN"),
    ("tax", "SALES TAX"),
    ("unassigned", "UNASSIGNED"),
)
COLUMN_KEYS = tuple(k for k, _ in COLUMNS)
# The lower block's groupings — the tab's L58:L61.
MATERIAL_COLUMNS = ("forms_accessories", "grade_material", "poly_sealing", "pt_cables",
                    "rebar", "rebar_accessories", "concrete", "seal_cure")
LABOR_COLUMNS = ("labor",)
SUB_LABOR_COLUMNS = ("sub_labor", "other_subs")
OTHER_COLUMNS = ("out_of_town", "equipment", "supervision", "pm")
# The tab's L57: labor insurance at 2.5% of sub labor, labor and supervision.
# Informational — the tab's ESTIMATED PROFIT does not subtract it.
LABOR_INSURANCE_PCT = Decimal("0.025")

# Lines that are not on a line set, named for the Settings screen.
PURCHASE_LABELS = {
    "concrete": "Concrete", "wall_concrete": "Wall concrete", "footing_concrete": "Footing concrete",
    "rebar": "Rebar", "mesh": "Wire mesh", "pt": "Post-tension", "sand": "Sand",
    "poly": "Vapor barrier", "tape": "Seam tape", "weld_plates": "Weld plates", "drilling": "Drilling",
    "rounding": "Per-row rounding (cents)",
}
MISC_LABELS = {
    "forms": "Misc item forms allowance", "labor": "Misc item labor allowance",
    "supervision": "Misc item supervision allowance", "equipment": "Misc item equipment allowance",
}
UPLIFT_LABELS = {"fuel": "Fuel & maintenance on rental days"}
KIND_LABELS = {
    "purchase": "Purchase", "material": "Forming materials", "labor": "Labor & supervision",
    "equipment": "Equipment & contract", "misc": "Miscellaneous item", "uplift": "Uplift",
}


def _d(x: Any) -> Decimal:
    return Decimal(str(x)) if x is not None and x != "" else _ZERO


@dataclass
class Line:
    """One priced line of a section, on its way to a cost code."""

    kind: str
    code: str
    label: str
    qty: Decimal | None
    unit: str | None
    cost: Decimal
    group: str | None = None
    inhouse: bool = False
    cost_code: str | None = None
    column: str = "unassigned"

    @property
    def is_labor(self) -> bool:
        """A line the section's Y/N routes: field labor, or a misc item's labor."""
        return (self.kind == "labor" and self.group == "labor") or (self.kind == "misc" and self.code == "labor")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "label": self.label,
            "qty": self.qty.quantize(_Q4) if self.qty is not None else None,
            "unit": self.unit,
            "cost": self.cost.quantize(_Q2),
            "group": self.group,
            "inhouse": self.inhouse,
            "cost_code": self.cost_code,
            "column": self.column,
        }


# ------------------------------------------------------------- the chart ----


def load_chart(db: Session) -> tuple[list[CostCode], dict[tuple[str, str], CostCodeLine]]:
    codes = list(db.scalars(select(CostCode).order_by(CostCode.sort_order, CostCode.code)).all())
    mapping = {(m.line_kind, m.line_code): m for m in db.scalars(select(CostCodeLine)).all()}
    return codes, mapping


def code_read(c: CostCode) -> dict[str, Any]:
    return {
        "code": c.code,
        "name": c.name,
        "category": c.category,
        "category_label": CATEGORY_LABELS.get(c.category, c.category),
        "summary_column": c.summary_column,
        "is_subtotal": bool(c.is_subtotal),
        "sort_order": c.sort_order,
    }


def _file(line: Line, by_code: dict[str, CostCode], mapping: dict[tuple[str, str], CostCodeLine]) -> None:
    """Give a line its code and its column, or leave it unassigned."""
    m = mapping.get((line.kind, line.code))
    if m is None:
        line.cost_code, line.column = None, "unassigned"
        return
    code = m.inhouse_code if (line.inhouse and m.inhouse_code) else m.cost_code
    line.cost_code = code
    cc = by_code.get(code)
    if line.is_labor:
        # The tab's Y/N column: in house is LABOR, subbed is SUB LABOR,
        # whatever the code — the chart has no in-house forming code and
        # in-house forming is still in-house labor.
        line.column = "labor" if line.inhouse else "sub_labor"
    elif cc is not None and cc.summary_column and not cc.is_subtotal:
        line.column = cc.summary_column
    else:
        line.column = "unassigned"


# ---------------------------------------------------------- the lines ----


def _purchase_lines(db: Session, section: EstimateSection) -> tuple[list[Line], Decimal]:
    """The purchases the material-costs reader reports, and its per-row cents."""
    from app.services.material_costs import section_material_costs

    out = section_material_costs(db, section)
    lines = [
        Line("purchase", ln["key"], ln["label"], _d(ln["qty"]), ln["unit"], _d(ln["cost"]))
        for ln in out["lines"]
    ]
    return lines, _d(out["rounding"])


def _misc_lines(db: Session, section: EstimateSection) -> list[Line]:
    """A misc item's typed allowances (sql/078): in its direct cost, on no line set."""
    from app.models.misc_item import MiscItem

    rows = list(db.scalars(select(MiscItem).where(MiscItem.section_id == section.id)).all())
    forms = sum((_d(r.calc_forms_cost) for r in rows), _ZERO)
    sup = sum((_d(r.calc_super_cost) for r in rows), _ZERO)
    equip = sum((_d(r.calc_equip_cost) for r in rows), _ZERO)
    labor_sub = sum((_d(r.calc_labor_cost) for r in rows if r.subcontracted), _ZERO)
    labor_in = sum((_d(r.calc_labor_cost) for r in rows if not r.subcontracted), _ZERO)
    lines: list[Line] = []
    if forms:
        lines.append(Line("misc", "forms", MISC_LABELS["forms"], None, None, forms))
    if labor_sub:
        lines.append(Line("misc", "labor", MISC_LABELS["labor"], None, None, labor_sub))
    if labor_in:
        lines.append(Line("misc", "labor", MISC_LABELS["labor"] + " (in house)", None, None, labor_in, inhouse=True))
    if sup:
        lines.append(Line("misc", "supervision", MISC_LABELS["supervision"], None, None, sup))
    if equip:
        lines.append(Line("misc", "equipment", MISC_LABELS["equipment"], None, None, equip))
    return lines


def _set_lines(db: Session, section: EstimateSection) -> list[Line]:
    """The three stored line sets, at what costing allocated: enabled lines with money on them."""
    lines: list[Line] = []
    for r in db.scalars(
        select(EstimateFormingLine).where(EstimateFormingLine.section_id == section.id)
        .order_by(EstimateFormingLine.sort_order, EstimateFormingLine.code)
    ).all():
        if r.enabled and _d(r.ext_cost) != 0:
            lines.append(Line("material", r.code, r.label, _d(r.qty), r.unit, _d(r.ext_cost)))
    subbed = bool(getattr(section, "labor_subcontracted", False))
    for r in db.scalars(
        select(EstimateLaborLine).where(EstimateLaborLine.section_id == section.id)
        .order_by(EstimateLaborLine.sort_order, EstimateLaborLine.code)
    ).all():
        if r.enabled and _d(r.ext_cost) != 0:
            lines.append(Line(
                "labor", r.code, r.label, _d(r.qty), r.unit, _d(r.ext_cost),
                group=r.group_name, inhouse=(r.group_name == "labor" and not subbed),
            ))
    for r in db.scalars(
        select(EstimateEquipmentLine).where(EstimateEquipmentLine.section_id == section.id)
        .order_by(EstimateEquipmentLine.sort_order, EstimateEquipmentLine.code)
    ).all():
        if r.enabled and _d(r.ext_cost) != 0:
            lines.append(Line(
                "equipment", r.code, r.label, _d(r.days_qty), r.unit, _d(r.ext_cost),
                group=r.group_name or "equipment",
            ))
    return lines


def _fuel(db: Session, section: EstimateSection) -> Decimal:
    """Fuel & maintenance as costing wrote it on the rows — rentals only, cents per row."""
    from app.services.costing import cost_units

    return sum((_d(getattr(u.row, "calc_equip_fuel", None)) for u in cost_units(db, section)), _ZERO)


def missing_line_sets(db: Session, section_id) -> list[str]:
    """Line sets nobody has built yet: absent from the summary AND from the section's cost."""
    out = []
    if db.get(EstimateFormingSummary, section_id) is None:
        out.append("forming")
    if db.get(EstimateLaborSummary, section_id) is None:
        out.append("labor")
    if db.get(EstimateEquipmentSummary, section_id) is None:
        out.append("equipment")
    return out


def section_lines(db: Session, section: EstimateSection) -> list[Line]:
    """Every dollar of a section's cost but the tax, as lines."""
    lines, residue = _purchase_lines(db, section)
    if section.kind in MISC_KINDS:
        misc = _misc_lines(db, section)
        residue -= sum((ln.cost for ln in misc), _ZERO)
        lines.extend(misc)
    if residue.quantize(_Q2) != 0:
        lines.append(Line("purchase", "rounding", PURCHASE_LABELS["rounding"], None, None, residue))
    lines.extend(_set_lines(db, section))
    fuel = _fuel(db, section)
    if fuel != 0:
        lines.append(Line("uplift", "fuel", UPLIFT_LABELS["fuel"], None, None, fuel))
    return lines


# --------------------------------------------------------- the summary ----


def contingency_share(sale: Decimal, cost: Decimal, margin_pct: Decimal, contingency_pct: Decimal) -> Decimal:
    """The contingency's share of the markup — the tab's 000091 (see the module docstring)."""
    both = _d(margin_pct) + _d(contingency_pct)
    if both <= 0:
        return _ZERO
    return ((sale - cost) * _d(contingency_pct) / both).quantize(_Q2)


def section_summary(
    db: Session,
    section: EstimateSection,
    chart: list[CostCode],
    mapping: dict[tuple[str, str], CostCodeLine],
) -> dict[str, Any]:
    by_code = {c.code: c for c in chart}
    lines = section_lines(db, section)
    for ln in lines:
        _file(ln, by_code, mapping)

    columns = {k: _ZERO for k in COLUMN_KEYS}
    codes = {c.code: _ZERO for c in chart}
    for ln in lines:
        columns[ln.column] += ln.cost
        if ln.cost_code in codes:
            codes[ln.cost_code] += ln.cost
    tax = _d(section.calc_total_tax)
    columns["tax"] = tax

    cost = _d(section.calc_total_cost)
    sale = _d(section.calc_total_sale)
    from_lines = sum(columns.values(), _ZERO)
    difference = (cost - from_lines).quantize(_Q2)
    contingency = contingency_share(sale, cost, section.margin_pct, section.contingency_pct)
    profit = (sale - cost - contingency).quantize(_Q2)
    codes["000091"] = contingency
    for c in chart:
        if c.is_subtotal:
            codes[c.code] = sum(
                (codes[o.code] for o in chart if o.category == c.category and not o.is_subtotal), _ZERO
            )

    qty = _d(section.calc_quantity)
    per_unit = {k: (v / qty).quantize(_Q4) for k, v in columns.items()} if qty > 0 else {}
    return {
        "id": section.id,
        "name": section.name,
        "kind": section.kind,
        "unit": section.unit,
        "quantity": section.calc_quantity,
        "sale": sale.quantize(_Q2),
        "cost": cost.quantize(_Q2),
        "tax": tax.quantize(_Q2),
        "sale_per_unit": section.calc_sale_per_unit,
        "cost_per_unit": section.calc_cost_per_unit,
        "margin_pct": _d(section.margin_pct),
        "contingency_pct": _d(section.contingency_pct),
        "labor_subcontracted": bool(getattr(section, "labor_subcontracted", False)),
        "columns": {k: v.quantize(_Q2) for k, v in columns.items()},
        "per_unit": per_unit,
        "codes": {k: v.quantize(_Q2) for k, v in codes.items()},
        "contingency": contingency,
        "profit": profit,
        "difference": difference,
        "missing_line_sets": missing_line_sets(db, section.id),
        "unassigned": [ln.as_dict() for ln in lines if ln.column == "unassigned"],
        "lines": [ln.as_dict() for ln in lines],
    }


def file_name(project: Project | None, estimate: Estimate, when: date | None = None) -> str:
    """`<Job Name> - Summary - <Job #> - <YYYY-MM-DD>.xlsx`, the proposal's pattern."""
    when = when or date.today()
    parts = [(project.name if project else estimate.name).strip(), "Summary"]
    if project is not None and project.job_number:
        parts.append(project.job_number.strip())
    parts.append(when.isoformat())
    return " - ".join(p for p in parts if p) + ".xlsx"


def estimate_summary(db: Session, estimate: Estimate) -> dict[str, Any]:
    """The whole tab: every section, the totals, the shares, the lower block, the chart."""
    project = db.get(Project, estimate.project_id)
    estimator = db.get(Estimator, estimate.estimator_id) if estimate.estimator_id else None
    chart, mapping = load_chart(db)
    sections = [
        section_summary(db, s, chart, mapping)
        for s in db.scalars(
            select(EstimateSection)
            .where(EstimateSection.estimate_id == estimate.id)
            .order_by(EstimateSection.sort_order, EstimateSection.created_at)
        ).all()
    ]

    columns = {k: sum((s["columns"][k] for s in sections), _ZERO).quantize(_Q2) for k in COLUMN_KEYS}
    codes = {c.code: sum((s["codes"][c.code] for s in sections), _ZERO).quantize(_Q2) for c in chart}
    sale = sum((s["sale"] for s in sections), _ZERO).quantize(_Q2)
    cost = sum((s["cost"] for s in sections), _ZERO).quantize(_Q2)
    contingency = sum((s["contingency"] for s in sections), _ZERO).quantize(_Q2)
    profit = sum((s["profit"] for s in sections), _ZERO).quantize(_Q2)
    difference = sum((s["difference"] for s in sections), _ZERO).quantize(_Q2)
    shares = {k: (v / sale).quantize(_Q4) for k, v in columns.items()} if sale > 0 else {}

    total_material = sum((columns[k] for k in MATERIAL_COLUMNS), _ZERO)
    total_labor = sum((columns[k] for k in LABOR_COLUMNS), _ZERO)
    total_sub_labor = sum((columns[k] for k in SUB_LABOR_COLUMNS), _ZERO)
    total_other = sum((columns[k] for k in OTHER_COLUMNS), _ZERO)
    insurance = ((columns["sub_labor"] + columns["labor"] + columns["supervision"]) * LABOR_INSURANCE_PCT).quantize(_Q2)
    lower = {
        "total_material": total_material,
        "total_labor": total_labor,
        "total_sub_labor": total_sub_labor,
        "total_other": total_other,
        "sales_tax": columns["tax"],
        "unassigned": columns["unassigned"],
        "margin_contingency": contingency,
        "estimated_profit": profit,
        "labor_insurance": insurance,
        "labor_insurance_pct": LABOR_INSURANCE_PCT,
        "contract_price": sale,
        "cost": cost,
        "difference": difference,
    }
    return {
        "estimate_id": estimate.id,
        "estimate_name": estimate.name,
        "estimate_status": estimate.status,
        "project_id": estimate.project_id,
        "project_name": project.name if project else None,
        "job_number": project.job_number if project else None,
        "gc": project.gc if project else None,
        "location": project.location if project else None,
        "estimator_name": estimator.full_name if estimator else None,
        "generated_at": datetime.now(timezone.utc),
        "file_name": file_name(project, estimate),
        "columns": [{"key": k, "label": label} for k, label in COLUMNS],
        "sections": sections,
        "totals": {"columns": columns, "codes": codes},
        "shares": shares,
        "lower": lower,
        "codes": [code_read(c) for c in chart],
    }


# ------------------------------------------------------ the settings screen ----


_SEEN_SQL = {
    "material": "SELECT DISTINCT ON (code) code, label FROM estimate_forming_lines ORDER BY code, updated_at DESC",
    "labor": "SELECT DISTINCT ON (code) code, label FROM estimate_labor_lines ORDER BY code, updated_at DESC",
    "equipment": "SELECT DISTINCT ON (code) code, label FROM estimate_equipment_lines ORDER BY code, updated_at DESC",
}


def lines_catalog(db: Session) -> list[dict[str, Any]]:
    """
    Every line the summary can meet, with where it is filed: the lines some
    section carries today, the purchases and allowances the readers report,
    and anything the table names that nothing carries yet.
    """
    _, mapping = load_chart(db)
    seen: dict[tuple[str, str], str] = {}
    for kind, sql in _SEEN_SQL.items():
        for code, label in db.execute(text(sql)).all():
            seen[(kind, code)] = label
    known: dict[tuple[str, str], str] = {}
    for code, label in PURCHASE_LABELS.items():
        known[("purchase", code)] = label
    for code, label in MISC_LABELS.items():
        known[("misc", code)] = label
    for code, label in UPLIFT_LABELS.items():
        known[("uplift", code)] = label

    keys = set(mapping) | set(seen) | set(known)
    order = {k: i for i, k in enumerate(LINE_KINDS)}
    rows = []
    for kind, code in sorted(keys, key=lambda k: (order.get(k[0], 99), k[1])):
        m = mapping.get((kind, code))
        rows.append({
            "kind": kind,
            "code": code,
            "label": seen.get((kind, code)) or known.get((kind, code)) or code,
            "cost_code": m.cost_code if m else None,
            "inhouse_code": m.inhouse_code if m else None,
            "seen": (kind, code) in seen or (kind, code) in known,
        })
    return rows
