"""
Cast-in-place elevated deck: what a level comes to.

Source: `08-CIP EL. DECK`, re-derived formula by formula. The sheet's nineteen
cost columns sum to $952,052.0214 against its stated $952,052.0215, so the
model below reproduces a understood sheet rather than an approximated one.
`claude/cip-deck-spec.md` has the full derivation; sql/052 has the decisions.

The sixth assembly, and the first that HANGS IN THE AIR. Everything unusual
about it follows from that: shoring, reshoring, a crane at $3,200/day, and
post-tension.

-----------------------------------------------------------------------------
The geometry, as the sheet computes it
-----------------------------------------------------------------------------

    slab CY     = area x thickness_in / 324 x (1 + waste_concrete)
    beam CY     = LN FT x (width/12 x height/324) x (1 + waste_concrete)

    slab rebar  = per MAT (top, bottom), spacing s inches:
                    2 / (s / 12) x area x lb_per_ft x (1 + waste_rebar)
    beam rebar  = LN FT x lb per LF x (1 + waste_rebar_beams)

    PT cable lb = area x 1.15                (levels with cable only)
    GB form ff  = LN FT x height / 12 x 2    <- BOTH faces; see below

`2 / (s/12) x area` is LF of bar for a two-way mat — the standard rule, and
the sheet writes it as `(s/12 + s/12) / (s/12 x s/12) x area`, which is the
same thing the long way round.

-----------------------------------------------------------------------------
Four things this file does DIFFERENTLY from the sheet
-----------------------------------------------------------------------------

1. GRADE BEAM FORM FEET ARE BOTH FACES. The sheet's `U53 = C53/12` is one
   face. Chad, 2026-09-04, asked whether a deck grade beam is formed on one
   side only: **"both faces — the sheet is light."** 240 FF becomes 480, and
   because that figure also drives the 2x4, 2x6, 2x10, plywood and stake
   lines, LBJ moves +$2,425.01 — $1,440 of GB forming labor and $985.01 of
   lumber.

2. EVERY BEAM SLOT CARRIES ITS OWN STEEL. The sheet's `AL` (slot 1) reads
   column O, lb per LF. `AM` (slot 2) reads column **Q**, which is CY per LF.
   `AN` (slot 3) reads column **S**, which is a header cell and empty. LBJ's
   level 2 is therefore charged **7 lb** for a 45 LF type-2 beam that weighs
   2,855.49 — 3,190.88 lb after the beam factor, about $2,244 of steel and
   $718 of tie-steel labor, live on this job.

   There are no slots here. A level holds as many beams as it holds.

3. ONE BAR WEIGHT, FROM THE CATALOG. The deck sheet uses `10.6870159` for the
   slab mats and `10.680159` for the beam schedule — two approximations of the
   same ASTM weight, disagreeing in the fourth decimal, on one tab. A #4 is
   0.668 lb/ft; `(4/16)^2 x 10.68 = 0.6675` and `x 10.687 = 0.6679`. The app
   reads `bar_weights`, as columns and piers already do. `sheet_mode` swaps
   both constants back in so the bid can still be reproduced deliberately.

4. RESHORING COVERS EVERY LEVEL. `K83 = C10+C12+C14+C16+C22+C24+C28` is a
   hand-picked list of rows that skips 18, 20, 26 and everything past 28. A
   level entered on one of those rows is reshored for free.

`sheet_mode` restores the workbook's two bar constants and nothing else. The
four decisions above are decisions, not options — the same call columns made.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.beam_type import EstimateBeamType
from app.models.deck_level import DeckLevel, DeckLevelBeam
from app.models.estimate_section import EstimateSection
from app.services.calc import _rate_numeric, _waste
from app.services.columns import bar_lb_per_ft, sheet_bar_lb_per_ft

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")

# in x ft per CY: `SF x thickness_in / 324` is the sheet's form of SF x ft / 27.
SF_IN_PER_CY = Decimal("324")

# The deck sheet's own bar weight for the SLAB MATS. The beam schedule on the
# same tab uses 10.680159 — the columns constant — which is why both are here.
_SHEET_MAT_CONST = Decimal("10.6870159")
_SHEET_TIE_CONST = Decimal("3.145") * Decimal("0.2836")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def _w(db: Session, size: int | None, sheet: bool, const: Decimal) -> Decimal:
    """One bar's lb/ft — ASTM, or the workbook constant under sheet_mode."""
    if not size:
        return Decimal("0")
    return sheet_bar_lb_per_ft(size, const) if sheet else bar_lb_per_ft(db, size)


# --------------------------------------------------------------- geometry ---


def slab_cy(area_sf: Any, thickness_in: Any) -> Decimal:
    """Pre-waste slab concrete: area x thickness / 324."""
    return (_d(area_sf) * _d(thickness_in) / SF_IN_PER_CY).quantize(_Q4)


def mat_rebar_lb(
    db: Session,
    area_sf: Any,
    size: int | None,
    spacing_in: Any,
    *,
    sheet: bool = False,
) -> Decimal:
    """
    One two-way mat over an area.

        LF of bar = 2 / (spacing_in / 12) x area
        lb        = LF x lb per ft

    A mat with no size or no spacing contributes nothing, rather than
    contributing a zero-weight bar over the whole deck.
    """
    sp = _d(spacing_in)
    if sp <= 0 or not size:
        return Decimal("0")
    lf = Decimal("2") / (sp / Decimal("12")) * _d(area_sf)
    return lf * _w(db, size, sheet, _SHEET_MAT_CONST)


def beam_lb_per_lf(
    db: Session, beam: EstimateBeamType, *, sheet: bool = False
) -> Decimal:
    """
    Pounds of steel in one linear foot of a deck grade beam.

        top bars        count x lb/ft
        bottom bars     count x lb/ft
        mid bars        count x 2 x lb/ft      <- the sheet doubles these
        stirrups        one hoop per spacing:
                          (2W + 2L) inches x lb/in x (12 / spacing)
        L bars          (12 / spacing) x length_ft x lb/ft

    The mid-bar doubling and the per-inch stirrup weight are both the sheet's,
    and both match the columns sheet cell for cell — same author, same block,
    copied across. The stirrup constant checks out: for a #4 that is
    0.0558 lb/in against ASTM's 0.668/12 = 0.0557.
    """
    const = Decimal("10.680159")
    total = Decimal("0")

    for count, size, mult in (
        (beam.top_bars_count, beam.top_bars_size, Decimal("1")),
        (beam.bottom_bars_count, beam.bottom_bars_size, Decimal("1")),
        (beam.mid_bars_count, beam.mid_bars_size, Decimal("2")),
    ):
        if count and size:
            total += Decimal(int(count)) * mult * _w(db, size, sheet, const)

    sp = _d(beam.stirrup_spacing_in)
    if beam.stirrup_size and sp > 0:
        perim_in = (_d(beam.width_in) + _d(beam.height_in)) * Decimal("2")
        hoops = Decimal("12") / sp
        if sheet:
            total += (
                sheet_bar_lb_per_ft(beam.stirrup_size, _SHEET_TIE_CONST)
                * perim_in
                * hoops
            )
        else:
            total += (
                perim_in / Decimal("12") * hoops * bar_lb_per_ft(db, beam.stirrup_size)
            )

    lsp = _d(beam.l_bars_spacing_in)
    if beam.l_bars_size and lsp > 0:
        length = _d(getattr(beam, "l_bars_length_ft", None))
        total += (
            Decimal("12") / lsp * length * _w(db, beam.l_bars_size, sheet, const)
        )

    return total


def beam_cy_per_lf(beam: EstimateBeamType) -> Decimal:
    """Pre-waste concrete in one linear foot: width/12 x height / 324."""
    return _d(beam.width_in) / Decimal("12") * _d(beam.height_in) / SF_IN_PER_CY


def beam_ff_per_lf(beam: EstimateBeamType, *, faces: int = 2) -> Decimal:
    """
    Form contact in one linear foot of beam: height / 12, times the faces.

    The sheet's `U53` is `C53/12` — ONE face. Chad, 2026-09-04: "both faces —
    the sheet is light." Two here, and it is worth $2,425.01 on LBJ because
    the section's whole lumber block rides this number.
    """
    return _d(beam.height_in) / Decimal("12") * Decimal(int(faces))


def pt_cable_lb(db: Session, area_sf: Any, kind: str | None) -> Decimal:
    """Cable weight for a post-tensioned level: area x lb per SF."""
    return (
        _d(area_sf) * _rate_numeric(db, kind, "pt_lb_per_sf", Decimal("1.15"))
    ).quantize(_Q3)


# ---------------------------------------------------------------- refresh ---


def refresh_deck_level_calcs(
    db: Session,
    row: DeckLevel,
    section: EstimateSection | None = None,
    *,
    sheet_mode: bool = False,
) -> DeckLevel:
    """Populate row.calc_* and its beams' from the takeoff. Caller commits."""
    if section is None:
        section = db.get(EstimateSection, row.section_id)
    if section is None:
        raise ValueError("section not found for deck level")
    kind = section.kind

    waste_c = Decimal("1") + _waste(section, db, "waste_concrete", "waste_concrete")
    waste_r = Decimal("1") + _waste(section, db, "waste_rebar", "waste_rebar")
    # Beam steel carries a second factor ON TOP of waste_rebar — the sheet's
    # `AO = SUM(...) x 1.12`, applied after the schedule row has already
    # multiplied by 1.10. 1.232 on a grade beam bar, and it is the sheet's.
    beam_extra = Decimal("1") + _rate_numeric(
        db, kind, "waste_rebar_beams", Decimal("0")
    )

    area = _d(row.area_sf)

    slab = slab_cy(area, row.thickness_in) * waste_c
    mats = (
        mat_rebar_lb(db, area, row.top_bar_size, row.top_bar_spacing_in, sheet=sheet_mode)
        + mat_rebar_lb(db, area, row.bot_bar_size, row.bot_bar_spacing_in, sheet=sheet_mode)
    ) * waste_r

    beam_cy = Decimal("0")
    beam_lb = Decimal("0")
    beam_ff = Decimal("0")
    beam_lf = Decimal("0")
    beams = list(
        db.scalars(
            select(DeckLevelBeam)
            .where(DeckLevelBeam.deck_level_id == row.id)
            .order_by(DeckLevelBeam.sort_order, DeckLevelBeam.created_at)
        ).all()
    )
    for b in beams:
        bt = b.beam_type or db.get(EstimateBeamType, b.beam_type_id)
        if bt is None:
            continue
        lf = _d(b.length_lf)
        cy = (beam_cy_per_lf(bt) * lf * waste_c).quantize(_Q4)
        lb = (beam_lb_per_lf(db, bt, sheet=sheet_mode) * lf * waste_r * beam_extra).quantize(_Q3)
        ff = (beam_ff_per_lf(bt) * lf).quantize(_Q3)
        b.calc_concrete_cy = cy
        b.calc_rebar_lb = lb
        b.calc_form_ff = ff
        beam_cy += cy
        beam_lb += lb
        beam_ff += ff
        beam_lf += lf

    row.calc_slab_cy = slab.quantize(_Q4)
    row.calc_beam_cy = beam_cy.quantize(_Q4)
    row.calc_concrete_cy = (slab + beam_cy).quantize(_Q4)
    row.calc_slab_rebar_lb = mats.quantize(_Q3)
    row.calc_beam_rebar_lb = beam_lb.quantize(_Q3)
    row.calc_total_rebar_lb = (mats + beam_lb).quantize(_Q3)
    row.calc_gb_form_ff = beam_ff.quantize(_Q3)
    row.calc_beam_lf = beam_lf.quantize(_Q3)
    # PT is the area of the levels that CARRY cable, not the whole deck —
    # the sheet's `BE10 = IF(F10="N", 0, C10)`.
    row.calc_pt_sf = area.quantize(_Q3) if row.has_cable else Decimal("0.000")
    row.calc_pt_lb = pt_cable_lb(db, row.calc_pt_sf, kind)
    return row


def refresh_section_deck_calcs(
    db: Session, section: EstimateSection, *, sheet_mode: bool = False
) -> int:
    rows = list(
        db.scalars(
            select(DeckLevel)
            .where(DeckLevel.section_id == section.id)
            .order_by(DeckLevel.sort_order, DeckLevel.created_at)
        ).all()
    )
    for row in rows:
        refresh_deck_level_calcs(db, row, section, sheet_mode=sheet_mode)
    return len(rows)


def super_days(db: Session, section_id: Any) -> Decimal:
    """
    A deck TYPES its days, like piers and walls.

    Nothing on the sheet derives them: `D100` is entered (60 on LBJ) and
    everything downstream — foreman, expense, PM, and the whole rental ladder —
    reads it. Untyped, that ladder is zero days and every machine prices at
    $0.00 beside a correct rate, which is audit #5 and why this assembly
    inherits its warning.
    """
    typed = db.execute(
        text(
            "SELECT qty FROM estimate_labor_lines "
            "WHERE section_id = :sid AND code = 'superintendent'"
        ),
        {"sid": str(section_id)},
    ).scalar()
    return _d(typed)


def section_deck_totals(db: Session, section_id: Any) -> dict[str, Any]:
    """Rollup for a deck section. Mirrors section_column_totals."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS level_count,
              coalesce(sum(area_sf), 0) AS total_sf,
              coalesce(sum(perm_edge_lf), 0) AS total_perm_edge_lf,
              coalesce(sum(mesh_sf), 0) AS total_mesh_sf,
              coalesce(sum(calc_slab_cy), 0) AS total_slab_cy,
              coalesce(sum(calc_beam_cy), 0) AS total_beam_cy,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_slab_rebar_lb), 0) AS total_slab_rebar_lb,
              coalesce(sum(calc_beam_rebar_lb), 0) AS total_beam_rebar_lb,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_pt_sf), 0) AS total_pt_sf,
              coalesce(sum(calc_pt_lb), 0) AS total_pt_lb,
              coalesce(sum(calc_gb_form_ff), 0) AS total_gb_form_ff,
              coalesce(sum(calc_beam_lf), 0) AS total_beam_lf,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost,
              coalesce(sum(calc_sale), 0) AS total_sale
            FROM deck_levels
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    sf = _d(out.get("total_sf"))
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    # The lumber block, the nails and the GB forming labor all ride this one
    # figure, which is why it is a rollup and not a detail.
    out["lumber_driver_lf"] = (
        _d(out.get("total_perm_edge_lf")) + _d(out.get("total_gb_form_ff"))
    ).quantize(_Q3)
    out["total_rebar_tons"] = (_d(out.get("total_rebar_lb")) / Decimal("2000")).quantize(_Q4)
    out["total_cost_per_unit"] = (cost / sf).quantize(_Q4) if sf > 0 else None
    out["total_sale_per_unit"] = (sale / sf).quantize(_Q4) if sf > 0 else None
    return out
