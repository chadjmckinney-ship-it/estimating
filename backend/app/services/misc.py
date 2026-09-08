"""
Miscellaneous: the 13-Miscellaneous tab as a priced library of site items
(sql/078).

The tab is not a takeoff. One row is an ITEM with a typed unit SALE (H) and
a typed LABOR cost a unit (J), a sub flag, and a shape the concrete and steel
come from. Four families, each a block of rows on the tab:

    round   dia" x depth'      CY = pi r^2 / 144 x depth / 27, wasted
                               steel = dia x depth x lb/(in.ft)         (the tab's 0.95)
    block   LF x W" x H"       CY = L x W x H / 3888, wasted, plus a FLOOR (L/4)^2 / 27
                               steel = CY x lb/CY (+ lb a unit)          (145 on a pit, 55 on a pad)
    slab    SF x thk"          CY = SF x thk / 324, wasted
                               steel = CY x lb/CY                        (1% of 13,232)
    box     L" x W" x D"       CY = L x W x D / 46656, wasted
                               steel = CY x lb/CY                        (0.5% of 13,325, or a ratio)

The rest of a row's cost is a typed ALLOWANCE with the tab's own formula as
its default: forms as a share of the sale plus dollars a unit, plus dollars a
face SF on a pit (L x H / 12), plus a share of the concrete on the slabs;
supervision as a share of labor; equipment as dollars a unit plus a share of
labor, with a minimum (the tab's IF(qty < 11, 300, qty x 30)). Every knob is
on the row instead of in 26 different formulas.

Concrete and steel price from the catalog at cost time and are taxed, as on
every other assembly. The tab rounds each row's CY UP to the yard and its
steel to the pound (the round bases and the blocks), and forgets the tax on
the first two families' concrete and steel; here the yards keep their
decimals and everything bought is taxed — the same two departures every
other tab reconciled.

The SALE is the typed sale, times the quantity. The margin is the answer:
1 - cost / sale on the row (the tab's Z) and for the section, and the
Summary reads this tab's sale as the sum of its rows. The first section
where the markup is a result rather than an input; the cost at the section's
markup shows beside it for comparison.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.estimate_section import EstimateSection
from app.models.misc_item import LIBRARY_FIELDS, MiscItem, MiscItemLibrary

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")

SHAPES = ("round", "block", "slab", "box")

# pi, not the tab's 3.145 — three parts in ten thousand on a light pole base.
PI = Decimal("3.14159265358979")
SQ_IN_FT_PER_CY = Decimal("3888")      # in x in x ft
SQ_FT_IN_PER_CY = Decimal("324")       # SF x in
CU_IN_PER_CY = Decimal("46656")        # in x in x in


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


# ------------------------------------------------------------- geometry ----


def concrete_cy_each(row: MiscItem) -> Decimal:
    """One item's concrete, WITH its waste — the tab's O column before the ROUNDUP and the count."""
    if not getattr(row, "pours_concrete", True):
        return Decimal("0")
    a, b, c = _d(row.dim_a), _d(row.dim_b), _d(row.dim_c)
    w = Decimal("1") + _d(row.concrete_waste)
    shape = row.shape
    if shape == "round":
        r = a / Decimal("2")
        return PI * r * r / Decimal("144") * b / Decimal("27") * w
    if shape == "block":
        # The tab wastes the walls and lays an unwasted floor a quarter of the
        # length square under them: (L/4)^2 / 27.
        return a * b * c / SQ_IN_FT_PER_CY * w + (a / Decimal("4")) * (a / Decimal("4")) / Decimal("27")
    if shape == "slab":
        return a * b / SQ_FT_IN_PER_CY * w
    if shape == "box":
        return a * b * c / CU_IN_PER_CY * w
    return Decimal("0")


def steel_lb_each(row: MiscItem) -> Decimal:
    """One item's bar: lb a CY of its concrete, plus dia x depth x lb/(in.ft) on a round base, plus lb a unit."""
    lb = concrete_cy_each(row) * _d(row.steel_lb_per_cy) + _d(row.steel_lb_per_unit)
    if row.shape == "round":
        lb += _d(row.dim_a) * _d(row.dim_b) * _d(row.steel_lb_per_in_ft)
    return lb


def face_sf_each(row: MiscItem) -> Decimal:
    """A block's formed face, L x H / 12 — what the pit's $4.25 a SF of forms rides (Q17)."""
    if row.shape != "block":
        return Decimal("0")
    return _d(row.dim_a) * _d(row.dim_c) / Decimal("12")


# -------------------------------------------------------------- refresh ----


def refresh_misc_item_calcs(
    db: Session, row: MiscItem, section: EstimateSection | None = None
) -> MiscItem:
    """Populate the row's quantities and its typed sale. Caller commits; the money is costing's."""
    qty = _d(row.qty)
    row.calc_concrete_cy = (concrete_cy_each(row) * qty).quantize(_Q4)
    row.calc_steel_lb = (steel_lb_each(row) * qty).quantize(_Q3)
    row.calc_face_sf = (face_sf_each(row) * qty).quantize(_Q3)
    row.calc_sale = (_d(row.unit_sale) * qty).quantize(_Q2)
    return row


def refresh_section_misc_calcs(db: Session, section: EstimateSection) -> int:
    rows = list(
        db.scalars(
            select(MiscItem)
            .where(MiscItem.section_id == section.id)
            .order_by(MiscItem.sort_order, MiscItem.created_at)
        ).all()
    )
    for row in rows:
        refresh_misc_item_calcs(db, row, section)
    return len(rows)


# ---------------------------------------------------------------- seed ----


def seed_from_library(db: Session, section: EstimateSection) -> int:
    """
    Copy the tab's 22 named items onto a new section at NO quantity — Chad,
    2026-09-08: "have the 4 sections with the ones shown as defaults, minus
    the quantities". Idempotent: a section that already carries rows is left
    alone. Caller commits.
    """
    have = db.scalar(
        text("SELECT count(*) FROM misc_items WHERE section_id = :s"), {"s": str(section.id)}
    )
    if have:
        return 0
    n = 0
    for lib in db.scalars(select(MiscItemLibrary).order_by(MiscItemLibrary.shape, MiscItemLibrary.sort_order)).all():
        row = MiscItem(section_id=section.id, qty=Decimal("0"),
                       **{f: getattr(lib, f) for f in LIBRARY_FIELDS})
        db.add(row)
        db.flush()
        refresh_misc_item_calcs(db, row, section)
        n += 1
    db.flush()
    return n


# --------------------------------------------------------------- totals ----


def section_misc_totals(db: Session, section_id: Any, section: EstimateSection | None = None) -> dict[str, Any]:
    """Rollup for a miscellaneous section: the typed sale, the six pieces of cost, the margin that falls out."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS row_count,
              count(*) FILTER (WHERE qty > 0)::int AS item_count,
              coalesce(sum(qty), 0) AS total_qty,
              coalesce(sum(calc_sale), 0) AS total_sale,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_steel_lb), 0) AS total_steel_lb,
              coalesce(sum(calc_concrete_cost), 0) AS total_concrete_cost,
              coalesce(sum(calc_steel_cost), 0) AS total_steel_cost,
              coalesce(sum(calc_forms_cost), 0) AS total_forms_cost,
              coalesce(sum(calc_labor_cost), 0) AS total_labor_cost,
              coalesce(sum(calc_labor_cost) FILTER (WHERE subcontracted), 0) AS total_sub_labor_cost,
              coalesce(sum(calc_super_cost), 0) AS total_super_cost,
              coalesce(sum(calc_equip_cost), 0) AS total_equip_cost,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost
            FROM misc_items
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    out["total_margin"] = ((sale - cost) / sale).quantize(_Q4) if sale > 0 else None
    # What the section's own markup would have made of the cost — the number
    # every other section sells at, shown beside the typed sale.
    if section is None:
        section = db.get(EstimateSection, section_id)
    factor = Decimal("1") + _d(getattr(section, "margin_pct", None)) + _d(getattr(section, "contingency_pct", None))
    out["sale_at_markup"] = (cost * factor).quantize(_Q2)
    return out


def misc_drivers(db: Session, section_id: Any) -> dict[str, Any]:
    """The section's takeoff sums, for the section page and the line-set stubs."""
    row = db.execute(
        text(
            "SELECT count(*)::int AS row_count, count(*) FILTER (WHERE qty > 0)::int AS item_count, "
            "       coalesce(sum(calc_concrete_cy), 0) AS cy, coalesce(sum(calc_steel_lb), 0) AS lb, "
            "       coalesce(sum(calc_sale), 0) AS sale "
            "FROM misc_items WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    return {
        "row_count": int(row["row_count"] or 0),
        "item_count": int(row["item_count"] or 0),
        "total_concrete_cy": _d(row["cy"]),
        "total_rebar_lb": _d(row["lb"]),
        "total_sale": _d(row["sale"]),
    }
