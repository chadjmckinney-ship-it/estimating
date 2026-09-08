"""
Tilt-wall panels: the 12-PANELS tab, formula by formula (sql/077).

The row (the tab's row 10) is a panel TYPE with a count: mix, length,
thickness, top and bottom elevation, openings as L x W, a horizontal and a
vertical mat each as a spacing, a size and a count of mats, edge bars and
corner bars each as a count and a size. Chad seeded twelve types on the LBJ
workbook on 2026-09-08 and asked for four opening slots where the tab has
one — "right now we have to figure total opening size if more than 1
opening so it is actually short on rebar and lumber for the openings".

STEEL (U10), per panel, before waste:

    horizontal   L x H x 12 / spacing x mats x lb/ft
    vertical     H x 12 / spacing x L x mats x lb/ft
    edge bars    (n x L + n x H) x 2 x lb/ft
    openings     the same edge-bar set again, ONCE PER OPENING
    corner bars  n x 4 ft x lb/ft

The tab's opening term is `IF(I10>0, Q10*D10 + Q10*(F10-G10)*2*w)`: a copy
of the edge-bar term with its bracket dropped, so `Q x D` is added as bare
pounds — the same class of misplaced parenthesis the columns tab had on its
waste. The bracket is closed here, and the set is added per opening rather
than once per panel, which is the whole point of the four slots. Bar weight
is the catalog's; the tab reads (size/16)^2 x 10.7028, and `sheet_mode`
swaps that back in for reconciliation. Waste on every bar (J69).

CONCRETE (V10): (L x H - the openings' area) x thickness / 324, with waste.
Not rounded — the batch ticket rounds, the bid does not.

AREA (W10): L x H, GROSS. The tab prices its labor per SF of that and its
per-panel column divides by it; openings come off the concrete, not the
area. Kept as the tab keeps it: forming an opening is work, not less work.

PERIMETER (AT): (2L + 2H) x qty — what the lumber and the chamfer run off.
Each opening's perimeter (2L + 2W) x qty joins it (`calc_opening_lf`): a
blockout is formed like an edge, and the tab carries no opening lumber.

BOTTOM (AU): L x qty — the carton forms, the durrock retainer and the
backfill trench run along it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.estimate_section import EstimateSection
from app.models.panel_type import PanelType
from app.services.calc import _rate_numeric, _waste
from app.services.walls import bar_lb_per_ft

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")

# SF x inches / 324 = CY (12 x 27). The tab writes D x E/12 x H / 27 for the
# panel and I x J x E / 324 for the opening; they are the same constant.
SQ_FT_IN_PER_CY = Decimal("324")
# The tab's bar weight, (size/16)^2 x 10.7028 lb/ft — reconciliation only.
_SHEET_BAR_CONST = Decimal("10.7028")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def sheet_bar_lb_per_ft(size: int | None) -> Decimal:
    """The tab's own bar weight, for reproducing its steel."""
    if not size:
        return Decimal("0")
    s = Decimal(str(size)) / Decimal("16")
    return s * s * _SHEET_BAR_CONST


def _w(db: Session, size: int | None, sheet: bool) -> Decimal:
    return sheet_bar_lb_per_ft(size) if sheet else bar_lb_per_ft(db, size)


# ------------------------------------------------------------- geometry ----


def height_ft(top_el_ft: Any, bot_el_ft: Any) -> Decimal:
    """Top less bottom; a panel typed upside down is no panel, not a negative one."""
    h = _d(top_el_ft) - _d(bot_el_ft)
    return h if h > 0 else Decimal("0")


def openings(row: PanelType) -> list[tuple[Decimal, Decimal]]:
    """The openings that exist — a slot needs both a length and a width."""
    out: list[tuple[Decimal, Decimal]] = []
    for n in (1, 2, 3, 4):
        length = _d(getattr(row, f"open{n}_len_ft", None))
        wide = _d(getattr(row, f"open{n}_wide_ft", None))
        if length > 0 and wide > 0:
            out.append((length, wide))
    return out


def opening_sf_each(row: PanelType) -> Decimal:
    return sum((length * wide for length, wide in openings(row)), Decimal("0"))


def opening_lf_each(row: PanelType) -> Decimal:
    return sum((Decimal("2") * (length + wide) for length, wide in openings(row)), Decimal("0"))


def sf_each(row: PanelType) -> Decimal:
    """L x H, gross — the tab's W."""
    return _d(row.length_ft) * height_ft(row.top_el_ft, row.bot_el_ft)


def perimeter_lf_each(row: PanelType) -> Decimal:
    """2L + 2H — the tab's AT, per panel."""
    return Decimal("2") * (_d(row.length_ft) + height_ft(row.top_el_ft, row.bot_el_ft))


def concrete_cy_each(row: PanelType) -> Decimal:
    """(L x H - openings) x thickness / 324, before waste — the tab's V."""
    net_sf = sf_each(row) - opening_sf_each(row)
    if net_sf < 0:
        net_sf = Decimal("0")
    return net_sf * _d(row.thickness_in) / SQ_FT_IN_PER_CY


# ---------------------------------------------------------------- steel ----


def horiz_lb_each(db: Session, row: PanelType, *, sheet: bool = False) -> Decimal:
    """The horizontal mat: L x H x 12 / spacing x mats x lb/ft (the tab's first term)."""
    sp = _d(row.horiz_spacing_in)
    mats = _d(row.horiz_mats)
    if sp <= 0 or mats <= 0 or not row.horiz_size:
        return Decimal("0")
    return (
        _d(row.length_ft) * height_ft(row.top_el_ft, row.bot_el_ft) * Decimal("12") / sp
        * mats * _w(db, row.horiz_size, sheet)
    )


def vert_lb_each(db: Session, row: PanelType, *, sheet: bool = False) -> Decimal:
    """The vertical mat: H x 12 / spacing x L x mats x lb/ft (the second term)."""
    sp = _d(row.vert_spacing_in)
    mats = _d(row.vert_mats)
    if sp <= 0 or mats <= 0 or not row.vert_size:
        return Decimal("0")
    return (
        height_ft(row.top_el_ft, row.bot_el_ft) * Decimal("12") / sp * _d(row.length_ft)
        * mats * _w(db, row.vert_size, sheet)
    )


def edge_set_lb_each(db: Session, row: PanelType, *, sheet: bool = False) -> Decimal:
    """One set of edge bars: (n x L + n x H) x 2 x lb/ft — the tab's third term, and its opening term."""
    n = _d(row.edge_bar_count)
    if n <= 0 or not row.edge_bar_size:
        return Decimal("0")
    return (
        (n * _d(row.length_ft) + n * height_ft(row.top_el_ft, row.bot_el_ft))
        * Decimal("2") * _w(db, row.edge_bar_size, sheet)
    )


def corner_lb_each(db: Session, row: PanelType, corner_ft: Decimal, *, sheet: bool = False) -> Decimal:
    """Corner bars: n x 4 ft x lb/ft — the tab's last term."""
    n = _d(row.corner_bar_count)
    if n <= 0 or not row.corner_bar_size:
        return Decimal("0")
    return n * corner_ft * _w(db, row.corner_bar_size, sheet)


def steel_lb_each(
    db: Session, row: PanelType, *, corner_ft: Decimal = Decimal("4"), sheet: bool = False
) -> Decimal:
    """One panel's bar before waste: the mats, the edges, a set per opening, the corners."""
    edge = edge_set_lb_each(db, row, sheet=sheet)
    n_open = Decimal(len(openings(row)))
    return (
        horiz_lb_each(db, row, sheet=sheet)
        + vert_lb_each(db, row, sheet=sheet)
        + edge * (Decimal("1") + n_open)
        + corner_lb_each(db, row, corner_ft, sheet=sheet)
    )


# -------------------------------------------------------------- refresh ----


def refresh_panel_type_calcs(
    db: Session,
    row: PanelType,
    section: EstimateSection | None = None,
    *,
    sheet_mode: bool = False,
) -> PanelType:
    """
    Populate row.calc_* from the schedule. Caller commits.

    `sheet_mode` swaps in the tab's bar constant so a reconciliation can
    reproduce its steel to the pound. It does NOT reopen the bracket or put
    the opening set back to once per panel — those are decisions.
    """
    if section is None:
        section = db.get(EstimateSection, row.section_id)
    if section is None:
        raise ValueError("section not found for panel type")

    kind = getattr(section, "kind", None)
    waste_c = _waste(section, db, "waste_concrete", "waste_concrete")
    waste_r = _waste(section, db, "waste_rebar", "waste_rebar")
    corner_ft = _rate_numeric(db, kind, "corner_bar_ft", Decimal("4"))
    qty = Decimal(int(row.qty or 0))

    row.calc_height_ft = height_ft(row.top_el_ft, row.bot_el_ft).quantize(_Q3)
    row.calc_sf_each = sf_each(row).quantize(_Q3)
    row.calc_sf = (sf_each(row) * qty).quantize(_Q3)
    row.calc_opening_sf = (opening_sf_each(row) * qty).quantize(_Q3)
    row.calc_opening_lf = (opening_lf_each(row) * qty).quantize(_Q3)
    row.calc_perimeter_lf = (perimeter_lf_each(row) * qty).quantize(_Q3)
    row.calc_bottom_lf = (_d(row.length_ft) * qty).quantize(_Q3)
    row.calc_concrete_cy = (
        concrete_cy_each(row) * (Decimal("1") + waste_c) * qty
    ).quantize(_Q4)

    each = steel_lb_each(db, row, corner_ft=corner_ft, sheet=sheet_mode) * (Decimal("1") + waste_r)
    row.calc_steel_each_lb = each.quantize(_Q3)
    row.calc_total_rebar_lb = (each * qty).quantize(_Q3)
    return row


def refresh_section_panel_calcs(
    db: Session, section: EstimateSection, *, sheet_mode: bool = False
) -> int:
    rows = list(
        db.scalars(
            select(PanelType)
            .where(PanelType.section_id == section.id)
            .order_by(PanelType.sort_order, PanelType.created_at)
        ).all()
    )
    for row in rows:
        refresh_panel_type_calcs(db, row, section, sheet_mode=sheet_mode)
    return len(rows)


# --------------------------------------------------------------- totals ----


def section_panel_totals(db: Session, section_id: Any) -> dict[str, Any]:
    """Rollup for a panels section. Mirrors section_column_totals."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS type_count,
              coalesce(sum(qty), 0)::int AS panel_count,
              coalesce(sum(calc_sf), 0) AS total_sf,
              coalesce(sum(calc_opening_sf), 0) AS total_opening_sf,
              coalesce(sum(calc_opening_lf), 0) AS total_opening_lf,
              coalesce(sum(calc_perimeter_lf), 0) AS total_perimeter_lf,
              coalesce(sum(calc_bottom_lf), 0) AS total_bottom_lf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost,
              coalesce(sum(calc_sale), 0) AS total_sale
            FROM panel_types
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    n = Decimal(int(out.get("panel_count") or 0))
    sf = _d(out.get("total_sf"))
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    out["total_cost_per_unit"] = (cost / sf).quantize(_Q4) if sf > 0 else None
    out["total_sale_per_unit"] = (sale / sf).quantize(_Q4) if sf > 0 else None
    out["cost_per_panel"] = (cost / n).quantize(_Q4) if n > 0 else None
    out["sale_per_panel"] = (sale / n).quantize(_Q4) if n > 0 else None
    return out


def panel_drivers(db: Session, section_id: Any, *, thick_from_in: Any = None) -> dict[str, Any]:
    """
    The section's takeoff sums, for the three line sets.

    `thick_from_in` splits the formed perimeter (edges and openings) by the
    panel's thickness — 2x6 under it, 2x8 from it (the tab's AV / AW, which
    test `< 6` and `> 5.5` and so count a 5.75" panel twice; here a panel is
    one or the other). None means everything is thick.
    """
    t = _d(thick_from_in) if thick_from_in is not None else Decimal("0")
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS row_count,
              count(*) FILTER (WHERE qty > 0)::int AS type_count,
              coalesce(sum(qty), 0)::int AS panel_count,
              coalesce(sum(calc_sf), 0) AS total_sf,
              coalesce(sum(calc_opening_sf), 0) AS opening_sf,
              coalesce(sum(calc_opening_lf), 0) AS opening_lf,
              coalesce(sum(calc_perimeter_lf), 0) AS perimeter_lf,
              coalesce(sum(calc_bottom_lf), 0) AS bottom_lf,
              coalesce(sum(calc_perimeter_lf + coalesce(calc_opening_lf, 0))
                       FILTER (WHERE thickness_in < :t), 0) AS thin_lf,
              coalesce(sum(calc_perimeter_lf + coalesce(calc_opening_lf, 0))
                       FILTER (WHERE thickness_in >= :t), 0) AS thick_lf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb
            FROM panel_types
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id), "t": t},
    ).mappings().one()
    return {
        "row_count": int(row["row_count"] or 0),
        "type_count": int(row["type_count"] or 0),
        "panel_count": int(row["panel_count"] or 0),
        "total_sf": _d(row["total_sf"]),
        "opening_sf": _d(row["opening_sf"]),
        "opening_lf": _d(row["opening_lf"]),
        "perimeter_lf": _d(row["perimeter_lf"]),
        "bottom_lf": _d(row["bottom_lf"]),
        "thin_lf": _d(row["thin_lf"]),
        "thick_lf": _d(row["thick_lf"]),
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "total_rebar_lb": _d(row["total_rebar_lb"]),
    }
