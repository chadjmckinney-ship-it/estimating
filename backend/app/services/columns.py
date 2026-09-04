"""
Columns: what a cast-in-place column type comes to.

Source: `07-COLUMNS`, re-derived formula by formula. The sheet's steel
expression was reproduced in full and reproduces its own rows to four decimals
(44,825.9163 lb across the four LBJ types), so the model below is understood
rather than approximated. `claude/columns-spec.md` has the full derivation.

Three things this file does DIFFERENTLY from the sheet, all three Chad's call
on 2026-09-01, all three with a test:

1. WASTE APPLIES TO EVERY BAR. The sheet's bracket closes after the first
   vertical set, so its 10% lands on sets 2 and 3, the ties and the dowels —
   but not on the biggest bar in the cage. It reads as a misplaced parenthesis
   rather than a decision. +2,479 lb on LBJ.

2. FORM AREA IS PERIMETER x HEIGHT. The sheet computes
   `height x (L x W / 36) / 2`, which is a cross-section rather than a
   perimeter and runs light by an amount that varies with the column's
   proportions — 85.7% on an 18x24, 93.8% on an 18x30. The honest figure is
   `(L + W) x 2 / 12 x height`.

   The sheet already contains it. Column X, "Build up", is exactly that
   expression and totals 7,716 SF against the 6,660 the rest of the sheet
   uses. It drives one labor line and nothing else. This is the expensive
   difference: form area is also the basis every shared cost allocates by.

3. CHAMFER COUNTS THE COLUMNS. The sheet's `S81` is `SUM(height column) x 4`,
   summing the four TYPE heights and never multiplying by quantity — 240 LF on
   a 68-column job against 4,368. Same class as the paving 2x4 bracing range
   that summed a section-number column into a length column.

And one the sheet does that is right for ordering and wrong for costing:
CONCRETE IS NOT ROUNDED UP. `ROUNDUP(..., 0)` turns 52.6933 CY into 53 per
type. Sensible when you are calling the batch plant; the app keeps decimals
here as it does everywhere else, and the difference is 1.73 CY.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.column_type import ColumnType
from app.models.estimate_section import EstimateSection
from app.services.calc import _rate_numeric, _waste

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")

# in²·ft per CY (12 x 12 x 27). The sheet writes it as `F * G/12 * H / 324`,
# which is the same thing with one of the twelves moved. Same constant walls
# and grade beams use wherever inches x inches x feet becomes CY.
CU_IN_FT_PER_CY = Decimal("3888")

# The workbook's bar weight, (size/16)² x 10.680159 lb/ft, and its tie weight,
# which is the same idea expressed per INCH: (size/16)² x 3.145 x 0.2836. Both
# are here for `sheet=True` reconciliation only — the app uses ASTM.
_SHEET_BAR_CONST = Decimal("10.680159")
_SHEET_DOWEL_CONST = Decimal("10.703064")
_SHEET_TIE_CONST = Decimal("3.145") * Decimal("0.2836")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def bar_lb_per_ft(db: Session, size: int | None) -> Decimal:
    """ASTM weight for a bar size, from the locked bar_weights table."""
    if not size:
        return Decimal("0")
    row = db.execute(
        text("SELECT weight_lb_per_ft FROM bar_weights WHERE bar_size = :s"),
        {"s": int(size)},
    ).scalar()
    return _d(row)


def sheet_bar_lb_per_ft(size: int | None, const: Decimal = _SHEET_BAR_CONST) -> Decimal:
    """The workbook's own bar weight, for reconciling against it."""
    if not size:
        return Decimal("0")
    s = Decimal(str(size)) / Decimal("16")
    return s * s * const


def _w(db: Session, size: int | None, sheet: bool) -> Decimal:
    return sheet_bar_lb_per_ft(size) if sheet else bar_lb_per_ft(db, size)


# --------------------------------------------------------------- geometry ---


def formed_perimeter_in(length_in: Any, width_in: Any, faces: Any = 4) -> Decimal:
    """
    Inches of form around one column type — the faces you actually build.

        4   free-standing column       2L + 2W
        3   pilaster on a built wall    L + 2W    the wall side needs no form
        2   monolithic with the wall       2W     the wall's gang form carries
                                                  the outer face

    **The unformed face is always an L face** (sql/051): enter L along the
    wall and W as the projection out of it. A pilaster is a short column
    (sql/041) and differs from one here and almost nowhere else — but this is
    the difference that matters, because form SF is also the basis this
    section allocates every shared cost by.
    """
    length = _d(length_in)
    width = _d(width_in)
    n = int(_d(faces) or 4)
    l_faces = {4: Decimal("2"), 3: Decimal("1"), 2: Decimal("0")}.get(n, Decimal("2"))
    return length * l_faces + width * Decimal("2")


def formed_corners(faces: Any = 4) -> Decimal:
    """
    Chamfered corners on one column. Four when it is wrapped; two when a face
    sits against a wall, because that corner is a joint, not an edge.
    """
    return Decimal("4") if int(_d(faces) or 4) >= 4 else Decimal("2")


def form_sf(
    height_ft: Any, length_in: Any, width_in: Any, qty: Any, faces: Any = 4
) -> Decimal:
    """
    Form contact area: the faces you actually wrap, times the count.

        formed perimeter / 12 x height x qty

    NOT the sheet's `height x (L x W / 36) / 2`, which multiplies the two
    dimensions instead of adding them and therefore is not an area of anything.
    See the module docstring — the sheet holds this same expression one column
    over and uses it for a single labor line.

    `faces` defaults to 4, so a column is unchanged and only a pilaster row
    has to say anything.
    """
    per_column = (
        formed_perimeter_in(length_in, width_in, faces) / Decimal("12") * _d(height_ft)
    )
    return (per_column * _d(qty)).quantize(_Q4)


def sheet_form_sf(height_ft: Any, length_in: Any, width_in: Any, qty: Any) -> Decimal:
    """The sheet's `AZ` — kept so the bid can be reproduced deliberately."""
    per_column = (
        _d(height_ft) * _d(width_in) * _d(length_in) / Decimal("36") / Decimal("2")
    )
    return (per_column * _d(qty)).quantize(_Q4)


def concrete_cy(height_ft: Any, length_in: Any, width_in: Any, qty: Any) -> Decimal:
    """Pre-waste concrete: height x L/12 x W/12 x qty, in CY."""
    return (
        _d(height_ft) * _d(length_in) * _d(width_in) / CU_IN_FT_PER_CY * _d(qty)
    ).quantize(_Q4)


def chamfer_lf(height_ft: Any, qty: Any, faces: Any = 4) -> Decimal:
    """Every exposed corner, full height — four wrapped, two against a wall."""
    return (_d(height_ft) * formed_corners(faces) * _d(qty)).quantize(_Q3)


def vert_rebar_lb(
    db: Session, row: ColumnType, *, sheet: bool = False
) -> Decimal:
    """
    Every vertical bar, all three sets, full height. No lap: a column cage is
    cut to length, the same call piers made.
    """
    total = Decimal("0")
    for n, size in (
        (row.vert1_count, row.vert1_size),
        (row.vert2_count, row.vert2_size),
        (row.vert3_count, row.vert3_size),
    ):
        if not n or not size:
            continue
        total += _d(row.height_ft) * Decimal(int(n)) * _w(db, size, sheet)
    return total


def tie_rebar_lb(db: Session, row: ColumnType, *, sheet: bool = False) -> Decimal:
    """
    Ties: one hoop of the column's perimeter at every spacing, up the height.

        ties      = height x 12 / spacing
        hoop ft   = (L + W) x 2 / 12

    The sheet writes the same thing per inch —
    `(size/16)² x 3.145 x 0.2836 x perimeter_in x height x 12 / spacing` —
    and the constant checks out: for a #4 that is 0.0558 lb/in against ASTM's
    0.668/12 = 0.0557. No hook allowance here, unlike a pier hoop, because the
    sheet carries none and Chad has not asked for one.
    """
    sp = _d(row.tie_spacing_in)
    if sp <= 0 or not row.tie_size:
        return Decimal("0")
    perim_ft = (_d(row.length_in) + _d(row.width_in)) * Decimal("2") / Decimal("12")
    ties = _d(row.height_ft) * Decimal("12") / sp
    if sheet:
        # Reproduce the sheet's per-inch form exactly.
        perim_in = (_d(row.length_in) + _d(row.width_in)) * Decimal("2")
        return (
            sheet_bar_lb_per_ft(row.tie_size, _SHEET_TIE_CONST) * perim_in * ties
        )
    return perim_ft * ties * bar_lb_per_ft(db, row.tie_size)


def dowel_rebar_lb(db: Session, row: ColumnType, *, sheet: bool = False) -> Decimal:
    """The dowels that tie the column to whatever it lands on."""
    if not row.dowel_count or not row.dowel_size:
        return Decimal("0")
    w = (
        sheet_bar_lb_per_ft(row.dowel_size, _SHEET_DOWEL_CONST)
        if sheet
        else bar_lb_per_ft(db, row.dowel_size)
    )
    return Decimal(int(row.dowel_count)) * w * _d(row.dowel_length_ft)


# ---------------------------------------------------------------- refresh ---


def refresh_column_type_calcs(
    db: Session,
    row: ColumnType,
    section: EstimateSection | None = None,
    *,
    sheet_mode: bool = False,
) -> ColumnType:
    """
    Populate row.calc_* from the schedule. Caller commits.

    `sheet_mode` swaps in the workbook's bar weights and its cross-section form
    area, so a reconciliation can reproduce the bid exactly rather than
    approximately. It does NOT restore the sheet's missing vertical-bar waste
    or its chamfer bug — those are decided, not optional.
    """
    if section is None:
        section = db.get(EstimateSection, row.section_id)
    if section is None:
        raise ValueError("section not found for column type")

    waste_c = _waste(section, db, "waste_concrete", "waste_concrete")
    waste_r = _waste(section, db, "waste_rebar", "waste_rebar")
    qty = Decimal(int(row.qty or 0))

    # `sheet_mode` reproduces the workbook, and the workbook has no pilasters —
    # so faces apply to the honest figure only. Every sheet_mode row is a
    # wrapped column by definition.
    faces = getattr(row, "formed_faces", 4) or 4
    row.calc_form_sf = (
        sheet_form_sf(row.height_ft, row.length_in, row.width_in, qty)
        if sheet_mode
        else form_sf(row.height_ft, row.length_in, row.width_in, qty, faces)
    )
    row.calc_chamfer_lf = chamfer_lf(row.height_ft, qty, faces)
    row.calc_concrete_cy = (
        concrete_cy(row.height_ft, row.length_in, row.width_in, qty)
        * (Decimal("1") + waste_c)
    ).quantize(_Q4)

    rf = Decimal("1") + waste_r
    vert = vert_rebar_lb(db, row, sheet=sheet_mode) * qty * rf
    ties = tie_rebar_lb(db, row, sheet=sheet_mode) * qty * rf
    dowels = dowel_rebar_lb(db, row, sheet=sheet_mode) * qty * rf

    row.calc_vert_rebar_lb = vert.quantize(_Q3)
    row.calc_tie_rebar_lb = ties.quantize(_Q3)
    row.calc_dowel_rebar_lb = dowels.quantize(_Q3)
    row.calc_total_rebar_lb = (vert + ties + dowels).quantize(_Q3)
    return row


def refresh_section_column_calcs(
    db: Session, section: EstimateSection, *, sheet_mode: bool = False
) -> int:
    rows = list(
        db.scalars(
            select(ColumnType)
            .where(ColumnType.section_id == section.id)
            .order_by(ColumnType.sort_order, ColumnType.created_at)
        ).all()
    )
    for row in rows:
        refresh_column_type_calcs(db, row, section, sheet_mode=sheet_mode)
    return len(rows)


def super_days(db: Session, section_id: Any, kind: str | None) -> Decimal:
    """
    Columns derive their duration from a COUNT, on a FIVE-day week.

        weeks = columns / columns_per_super_week      68 / 20 = 3.4
        days  = weeks x labor_super_days_per_week     x 5     = 17

    Every other assembly either derives days from an area (slab SF/16,000,
    paving SF/25,000, both x 7) or types them (piers, walls). This is the first
    that counts things, and the first on a five-day week — a column crew is not
    on site seven days running. Both numbers are rates so neither is buried.

    Quantized ONCE at the end. Rounding weeks and then multiplying is a double
    round, and that is what cost the mono slab eight cents.
    """
    n = db.execute(
        text("SELECT coalesce(sum(qty), 0) FROM column_types WHERE section_id = :sid"),
        {"sid": str(section_id)},
    ).scalar()
    per_week = _rate_numeric(db, kind, "columns_per_super_week", Decimal("20"))
    days_per_week = _rate_numeric(db, kind, "labor_super_days_per_week", Decimal("5"))
    if per_week <= 0:
        return Decimal("0")
    return (_d(n) / per_week * days_per_week).quantize(_Q4)


def section_column_totals(db: Session, section_id: Any) -> dict[str, Any]:
    """Rollup for a columns section. Mirrors section_wall_totals."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS type_count,
              coalesce(sum(qty), 0)::int AS column_count,
              coalesce(sum(calc_form_sf), 0) AS total_form_sf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_vert_rebar_lb), 0) AS total_vert_rebar_lb,
              coalesce(sum(calc_tie_rebar_lb), 0) AS total_tie_rebar_lb,
              coalesce(sum(calc_dowel_rebar_lb), 0) AS total_dowel_rebar_lb,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_chamfer_lf), 0) AS total_chamfer_lf,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost,
              coalesce(sum(calc_sale), 0) AS total_sale
            FROM column_types
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    n = Decimal(int(out.get("column_count") or 0))
    sf = _d(out.get("total_form_sf"))
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    out["total_cost_per_unit"] = (cost / n).quantize(_Q4) if n > 0 else None
    out["total_sale_per_unit"] = (sale / n).quantize(_Q4) if n > 0 else None
    out["cost_per_form_sf"] = (cost / sf).quantize(_Q4) if sf > 0 else None
    return out
