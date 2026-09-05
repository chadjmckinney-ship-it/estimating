"""
Walls and footings: what a retaining wall and the footing under it come to.

Source: `06-Walls & Footings`, re-derived formula by formula. Every quantity
here was checked against the sheet's own numbers before a line of it was
written — form feet, footing SF, both concrete pours, all four steel terms,
sand, excavation and backfill all reproduce to the digit on all 16 LBJ rows.

Three things in this file look wrong and are not. Each has a test.

1. FOOTING STEEL IS ADDED TWICE, and that is correct. The sheet computes
   `E*(N/P)` and `(E/P)*N`, which are algebraically identical and read like a
   copy-paste duplicate. They are the two directions of a footing mat:
   longitudinal is N/P bars each E ft long; transverse is E*12/P bars each
   N/12 ft long. Both come to E*N/P. Same trap as the pier tie formula, same
   answer — the sheet is right. Since sql/059 the footing's two mats are
   each their own bar set (Chad: "there are times with footings when the top
   and bottom mat are different"); the doubling is per mat, and the footing's
   steel is the sum of its mats.

2. FORM FEET IS HALF THE CONTACT AREA. The sheet computes both faces of the
   wall and then halves the result. So "form feet" here means one face. That
   convention is worth $2.83/FF against $5.66/FF on the same job, so it is
   stated rather than assumed.

3. THERE IS A LAP ALLOWANCE HIDING IN THE PILASTER TERM. The sheet's steel
   formula ends `((T*U*S*0.03*0.2836*G)/12 + 4) * (G/H) * bar_lb`. T/U/S are
   pilaster dimensions; with no pilasters the product collapses and the bare
   `+ 4` survives, so every row with horizontal steel picks up 4 ft of bar per
   horizontal course. 12.5 lb on LBJ's biggest row, ~200 lb across the job,
   and part of the reconciled 33,727.83.

   Pilasters themselves are gone from this assembly (sql/041) -- Chad takes
   them off on the COLUMN sheet, because a pilaster is a short column and the
   wall sheet has nowhere to put a full schedule. What is left is the
   allowance, named and rated rather than buried in a formula.

One thing that IS wrong in the sheet and is not reproduced: the excavation
divisor. The sheet divides by **3088**, where every other in²·ft to CY
conversion in the workbook — including the footing concrete two columns over —
divides by 3888 (12 x 12 x 27). 3088 has no dimensional meaning. Using it
inflates excavation by 26%: 181 CY against 141, or $480 of excavation labor on
this job. `EXCAVATE_DIVISOR_SHEET` reproduces the sheet if you ever need the
bid back exactly.

Settled by Chad on 2026-09-05 with the workbook open: a typo, 3888 stays. The
evidence: the older template has no 3088 anywhere (its excavation was an
allocated labor line, not a per-row CY); 3088 arrived with the New Current
template's per-row excavation cell and was copied to all five walls-type
sheets by the same fill; every other inch x inch x ft to CY on the sheet is
3888 (286 cells); and the backfill cell beside it writes its 1.3 swell out
loud, which is what a deliberate allowance looks like.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.estimate_section import WALL_KINDS, EstimateSection
from app.models.wall_run import WallRun
from app.services.calc import _rate_numeric, _waste

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")

# in³ per CY (12 x 12 x 27), used wherever inches x inches x feet becomes CY.
CU_IN_FT_PER_CY = Decimal("3888")
# in³ per CY (1728 x 27), for the all-inches pilaster block.
CU_IN_PER_CY = Decimal("46656")

# The sheet's excavation divisor. Almost certainly a typo for 3888 — see the
# module docstring. Kept named so the bid can be reproduced deliberately.
EXCAVATE_DIVISOR_SHEET = Decimal("3088")

# The workbook's bar weight: (size/16)^2 x 10.680159 lb/ft. The app prefers the
# ASTM bar_weights table, and resolve happens through bar_lb_per_ft below.
_SHEET_BAR_CONST = Decimal("10.680159")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def bar_lb_per_ft(db: Session, size: int | None) -> Decimal:
    """ASTM weight for a bar size, from the locked bar_weights table."""
    if not size:
        return Decimal("0")
    row = db.execute(
        text("SELECT weight_lb_per_ft FROM bar_weights WHERE bar_size = :s"), {"s": int(size)}
    ).scalar()
    return _d(row)


def sheet_bar_lb_per_ft(size: int | None) -> Decimal:
    """The workbook's own bar weight, for reconciling against it."""
    if not size:
        return Decimal("0")
    s = Decimal(str(size)) / Decimal("16")
    return s * s * _SHEET_BAR_CONST


# --------------------------------------------------------------- geometry ---


def form_ff(length_ft: Any, height_in: Any) -> Decimal:
    """
    Form contact feet — ONE face.

    The sheet computes `L * H/12 * 2` (both faces) and then halves it. Halving
    is what makes $3.50/FF forming labor come out where it does, so the
    convention travels with the number.
    """
    both_faces = _d(length_ft) * _d(height_in) / Decimal("12") * Decimal("2")
    return (both_faces / Decimal("2")).quantize(_Q4)


def footing_sf(length_ft: Any, ftg_width_in: Any) -> Decimal:
    """Plan area of the footing — what footing labor is priced per."""
    return (_d(length_ft) * _d(ftg_width_in) / Decimal("12")).quantize(_Q4)


def wall_cy(length_ft: Any, thick_in: Any, height_in: Any) -> Decimal:
    return _d(length_ft) * _d(thick_in) * _d(height_in) / CU_IN_FT_PER_CY


def footing_cy(length_ft: Any, width_in: Any, thick_in: Any) -> Decimal:
    return _d(width_in) * _d(thick_in) * _d(length_ft) / CU_IN_FT_PER_CY


def sand_cy(form_feet: Any, depth_in: Decimal = Decimal("3")) -> Decimal:
    """
    Sand under the form line, rounded to whole CY per run as the sheet does.

    form_ff x depth_in / 27 — the sheet writes `BF*3/27`, so the 3 is inches of
    sand and the 27 turns square-feet-inches into CY only because 3/27 happens
    to be the right factor for a 3" layer. It is stated as a rate so a 4" spec
    does not silently keep costing 3".
    """
    return Decimal(round(_d(form_feet) * _d(depth_in) / Decimal("27")))


def excavate_cy(
    length_ft: Any,
    ftg_width_in: Any,
    ftg_thick_in: Any,
    divisor: Decimal = CU_IN_FT_PER_CY,
) -> Decimal:
    """
    Trench for the footing, whole CY. See the module docstring on the divisor.
    """
    return Decimal(
        round(_d(ftg_width_in) * _d(ftg_thick_in) / _d(divisor) * _d(length_ft))
    )


def backfill_cy(
    length_ft: Any, height_in: Any, swell: Decimal = Decimal("1.3")
) -> Decimal:
    """
    Backfill behind the wall, whole CY, with swell.

    The sheet's shape: a 3"-wide strip the full height plus a triangular wedge
    whose run equals the height —

        (H*0.25*L + H*H/144*0.5*L) / 27 * swell

    H*0.25 is inches x 0.25 = the strip in square feet per foot of run; the
    second term is the wedge. Both are the sheet's, not a standard.
    """
    h = _d(height_in)
    L = _d(length_ft)
    strip = h * Decimal("0.25") * L
    wedge = h * h / Decimal("144") * Decimal("0.5") * L
    return Decimal(round((strip + wedge) / Decimal("27") * _d(swell)))


# ------------------------------------------------------------------ steel ---


def horiz_rebar_lb(db, length_ft, height_in, spacing_in, size, mats, *, sheet=False) -> Decimal:
    """Bars running the length, repeated up the height."""
    sp = _d(spacing_in)
    if sp <= 0:
        return Decimal("0")
    w = sheet_bar_lb_per_ft(size) if sheet else bar_lb_per_ft(db, size)
    return _d(length_ft) * w * Decimal(int(mats or 0)) * (_d(height_in) / sp)


def vert_rebar_lb(db, length_ft, height_in, spacing_in, size, mats, *, sheet=False) -> Decimal:
    """Bars running the height, repeated along the length."""
    sp = _d(spacing_in)
    if sp <= 0:
        return Decimal("0")
    w = sheet_bar_lb_per_ft(size) if sheet else bar_lb_per_ft(db, size)
    return (
        _d(height_in) / Decimal("12") * w * Decimal(int(mats or 0))
        * (_d(length_ft) * Decimal("12") / sp)
    )


def footing_mat_lb(db, length_ft, width_in, spacing_in, size, *, sheet=False) -> Decimal:
    """
    ONE mat of footing steel, BOTH directions.

    Longitudinal: N/P bars, each E ft long          -> E * N/P
    Transverse:   E*12/P bars, each N/12 ft long    -> E * N/P

    Identical expressions, two real quantities. The sheet writes them as two
    terms and it is right to; see the module docstring. A mat with no spacing
    or no size is no mat.
    """
    sp = _d(spacing_in)
    if sp <= 0 or not size:
        return Decimal("0")
    w = sheet_bar_lb_per_ft(size) if sheet else bar_lb_per_ft(db, size)
    one_way = _d(length_ft) * (_d(width_in) / sp) * w
    return one_way * Decimal("2")


def footing_rebar_lb(
    db, length_ft, width_in, bot_spacing_in, bot_size, top_spacing_in, top_size, *, sheet=False
) -> Decimal:
    """
    The footing's steel: its bottom mat plus its top mat (sql/059).

    Until 2026-09-05 this was one bar set times a mat count -- the workbook's
    shape, right for LBJ (#5 @ 12" top and bottom on all 16 rows) and wrong for
    a footing whose mats differ. Chad: "there are times with footings when the
    top and bottom mat are different." Two identical mats come to exactly what
    "2 mats" came to, so the reconciled 33,727.83 lb does not move.
    """
    return footing_mat_lb(
        db, length_ft, width_in, bot_spacing_in, bot_size, sheet=sheet
    ) + footing_mat_lb(db, length_ft, width_in, top_spacing_in, top_size, sheet=sheet)


def lap_rebar_lb(
    db, height_in, horiz_spacing_in, horiz_size, *, lap_ft=Decimal("4"), sheet=False
) -> Decimal:
    """
    Lap allowance on horizontal steel: `lap_ft` of bar per horizontal course.

        lap_ft * (height / spacing) * bar_lb

    This is the bare `+ 4` the workbook leaves inside its pilaster term, which
    survives when there are no pilasters — and on Chad's jobs there never are,
    because pilasters go on the column sheet. Named and rated here rather than
    left looking like a stray keystroke.
    """
    sp = _d(horiz_spacing_in)
    if sp <= 0:
        return Decimal("0")
    w = sheet_bar_lb_per_ft(horiz_size) if sheet else bar_lb_per_ft(db, horiz_size)
    return _d(lap_ft) * (_d(height_in) / sp) * w


# ----------------------------------------------------------------- refresh --


def refresh_wall_run_calcs(
    db: Session, run: WallRun, section: EstimateSection | None = None, *, sheet_mode: bool = False
) -> WallRun:
    """
    Populate run.calc_* from the schedule. Caller commits.

    `sheet_mode` swaps in the workbook's bar weights and its 3088 excavation
    divisor, so a reconciliation can reproduce the bid exactly rather than
    approximately.
    """
    if section is None:
        section = db.get(EstimateSection, run.section_id)
    if section is None:
        raise ValueError("section not found for wall run")

    kind = getattr(section, "kind", None)
    waste_c = _waste(section, db, "waste_concrete", "waste_concrete")
    waste_r = _waste(section, db, "waste_rebar", "waste_rebar")
    sand_in = _rate_numeric(db, kind, "sand_in_under_form", Decimal("3"))
    swell = _rate_numeric(db, kind, "backfill_swell", Decimal("1.3"))

    L = _d(run.length_ft)
    H = _d(run.wall_height_in)

    # ------------------------------------------------------- quantities ----
    run.calc_form_ff = form_ff(L, H)
    run.calc_footing_sf = footing_sf(L, run.ftg_width_in)

    cf = Decimal("1") + waste_c
    wall = wall_cy(L, run.wall_thick_in, H)
    ftg = footing_cy(L, run.ftg_width_in, run.ftg_thick_in)
    run.calc_wall_concrete_cy = (wall * cf).quantize(_Q4)
    run.calc_footing_concrete_cy = (ftg * cf).quantize(_Q4)
    run.calc_concrete_cy = ((wall + ftg) * cf).quantize(_Q4)

    # ------------------------------------------------------------ steel ----
    rf = Decimal("1") + waste_r
    horiz = horiz_rebar_lb(
        db, L, H, run.horiz_spacing_in, run.horiz_size, run.horiz_mats, sheet=sheet_mode
    )
    vert = vert_rebar_lb(
        db, L, H, run.vert_spacing_in, run.vert_size, run.vert_mats, sheet=sheet_mode
    )
    foot = footing_rebar_lb(
        db, L, run.ftg_width_in,
        run.ftg_bot_spacing_in, run.ftg_bot_size, run.ftg_top_spacing_in, run.ftg_top_size,
        sheet=sheet_mode,
    )
    lap_ft = _rate_numeric(db, kind, "horiz_lap_ft_per_course", Decimal("4"))
    lapb = lap_rebar_lb(
        db, H, run.horiz_spacing_in, run.horiz_size, lap_ft=lap_ft, sheet=sheet_mode
    )
    run.calc_horiz_rebar_lb = (horiz * rf).quantize(_Q3)
    run.calc_vert_rebar_lb = (vert * rf).quantize(_Q3)
    run.calc_footing_rebar_lb = (foot * rf).quantize(_Q3)
    run.calc_lap_rebar_lb = (lapb * rf).quantize(_Q3)
    run.calc_total_rebar_lb = ((horiz + vert + foot + lapb) * rf).quantize(_Q3)

    # ------------------------------------------------- earth and drainage --
    # All three follow the backfill flag: an interior wall is not dug out,
    # sanded or drained.
    if run.backfill:
        run.calc_sand_cy = sand_cy(run.calc_form_ff, sand_in)
        run.calc_backfill_cy = backfill_cy(L, H, swell)
        run.calc_drain_lf = L.quantize(_Q3)
    else:
        run.calc_sand_cy = Decimal("0")
        run.calc_backfill_cy = Decimal("0")
        run.calc_drain_lf = Decimal("0")

    # Excavation runs regardless — the footing gets dug either way.
    divisor = EXCAVATE_DIVISOR_SHEET if sheet_mode else CU_IN_FT_PER_CY
    run.calc_excavate_cy = excavate_cy(L, run.ftg_width_in, run.ftg_thick_in, divisor)

    return run


def refresh_section_wall_calcs(
    db: Session, section: EstimateSection, *, sheet_mode: bool = False
) -> int:
    runs = list(
        db.scalars(
            select(WallRun)
            .where(WallRun.section_id == section.id)
            .order_by(WallRun.sort_order, WallRun.created_at)
        ).all()
    )
    for run in runs:
        refresh_wall_run_calcs(db, run, section, sheet_mode=sheet_mode)
    return len(runs)


def section_wall_totals(db: Session, section_id: Any) -> dict[str, Any]:
    """Rollup for a walls section. Mirrors section_pier_totals."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS run_count,
              coalesce(sum(length_ft), 0) AS total_length_ft,
              coalesce(sum(calc_form_ff), 0) AS total_form_ff,
              coalesce(sum(calc_footing_sf), 0) AS total_footing_sf,
              coalesce(sum(calc_wall_concrete_cy), 0) AS total_wall_concrete_cy,
              coalesce(sum(calc_footing_concrete_cy), 0) AS total_footing_concrete_cy,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_horiz_rebar_lb), 0) AS total_horiz_rebar_lb,
              coalesce(sum(calc_vert_rebar_lb), 0) AS total_vert_rebar_lb,
              coalesce(sum(calc_footing_rebar_lb), 0) AS total_footing_rebar_lb,
              coalesce(sum(calc_lap_rebar_lb), 0) AS total_lap_rebar_lb,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_sand_cy), 0) AS total_sand_cy,
              coalesce(sum(calc_excavate_cy), 0) AS total_excavate_cy,
              coalesce(sum(calc_backfill_cy), 0) AS total_backfill_cy,
              coalesce(sum(calc_drain_lf), 0) AS total_drain_lf,
              coalesce(sum(calc_wall_cost), 0) AS total_wall_cost,
              coalesce(sum(calc_wall_sale), 0) AS total_wall_sale,
              coalesce(sum(calc_footing_cost), 0) AS total_footing_cost,
              coalesce(sum(calc_footing_sale), 0) AS total_footing_sale,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost,
              coalesce(sum(calc_sale), 0) AS total_sale
            FROM wall_runs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    ff = _d(out.get("total_form_ff"))
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    out["total_cost_per_unit"] = (cost / ff).quantize(_Q4) if ff > 0 else None
    out["total_sale_per_unit"] = (sale / ff).quantize(_Q4) if ff > 0 else None

    # The two halves on their own drivers — the wall per form foot, the footing
    # per SF of plan area. These are the numbers to scan for a bad schedule.
    fsf = _d(out.get("total_footing_sf"))
    out["wall_cost_per_ff"] = (
        (_d(out["total_wall_cost"]) / ff).quantize(_Q4) if ff > 0 else None
    )
    out["wall_sale_per_ff"] = (
        (_d(out["total_wall_sale"]) / ff).quantize(_Q4) if ff > 0 else None
    )
    out["footing_cost_per_sf"] = (
        (_d(out["total_footing_cost"]) / fsf).quantize(_Q4) if fsf > 0 else None
    )
    out["footing_sale_per_sf"] = (
        (_d(out["total_footing_sale"]) / fsf).quantize(_Q4) if fsf > 0 else None
    )
    return out


# --------------------------------------------------- the wall/footing split --


def split_wall_and_footing(db: Session, section: EstimateSection) -> None:
    """
    Attribute each run's cost to the WALL and the FOOTING. Caller commits.

    One blended $/FF hides a bad footing schedule inside a plausible-looking
    wall rate. A 70" footing and a 36" wall share nothing but a length, so they
    are priced on their own drivers: the wall per FORM FOOT, the footing per
    SQUARE FOOT OF PLAN AREA.

    The rule:

        WALL      wall concrete, horizontal + vertical + lap steel, sand, the
                  forming package, forming/place/wreck/rub labor, backfill and
                  the french drain — both of those are against the wall
        FOOTING   footing concrete, footing steel, footing labor, excavation —
                  the trench is dug for the footing
        SHARED    supervision, equipment and anything else, split by form feet
                  against footing SF (the sheet's own basis, BF36 + BG36)

    Tie-steel labor follows the steel it ties and pumping follows the concrete,
    so both are attributed rather than pooled.

    **The footing half is computed and the wall takes the remainder.** That is
    the property that makes this worth having: the two can never sum to
    anything other than the row's own cost, so a discrepancy is always in the
    schedule and never in the arithmetic.

    Departs from the workbook on one point, on Chad's instruction: the sheet
    leaves ALL steel in the wall column, footing bar included — 51.7% of LBJ's
    rebar. Here the footing carries its own. See sql/042.
    """
    from app.services.costing import allocate_amount, tax_rate_for
    from app.services.labor import load_stored_labor

    kind = getattr(section, "kind", None)
    if kind not in WALL_KINDS:
        return

    runs = list(
        db.scalars(
            select(WallRun)
            .where(WallRun.section_id == section.id)
            .order_by(WallRun.sort_order, WallRun.created_at)
        ).all()
    )
    if not runs:
        return

    tax = tax_rate_for(db, section)
    taxed = Decimal("1") + tax

    # Labor rates come from the stored lines, not from assembly_rates — a line
    # the estimator has pinned by hand is what the section actually bills, and
    # the split has to follow the money that is really there.
    rates: dict[str, Decimal] = {}
    try:
        for ln in load_stored_labor(db, section.id)["lines"]:
            rates[ln["code"]] = _d(ln.get("rate"))
    except Exception:
        rates = {}

    def r(code: str, key: str, default: str) -> Decimal:
        if code in rates:
            return rates[code]
        return _rate_numeric(db, kind, key, Decimal(default))

    ftg_rate = r("footings", "labor_footings_sf", "8")
    exc_rate = r("excavate", "labor_excavate_cy", "12")
    tie_rate = r("tie_steel", "labor_tie_steel_ton", "450")
    rebar_cost = _rebar_price(db, kind)
    footing_mix = getattr(section, "footing_mix_design_id", None)

    footing_direct: list[Decimal] = []
    attributed: list[Decimal] = []

    for run in runs:
        ftg_cy = _d(run.calc_footing_concrete_cy)
        ftg_steel = _d(run.calc_footing_rebar_lb)
        ftg_sf = _d(run.calc_footing_sf)
        exc = _d(run.calc_excavate_cy)

        mix_id = footing_mix or run.mix_design_id
        ftg = (
            ftg_cy * _mix_price(db, mix_id) * taxed
            + ftg_steel * rebar_cost * taxed
            + ftg_sf * ftg_rate
            + exc * exc_rate
            + ftg_steel / Decimal("2000") * tie_rate
        )
        footing_direct.append(ftg.quantize(_Q2))

        # Everything on the row that is attributed to one side or the other.
        # What is left over after this is the shared pool.
        wall_cy = _d(run.calc_wall_concrete_cy)
        wall_steel = (
            _d(run.calc_horiz_rebar_lb)
            + _d(run.calc_vert_rebar_lb)
            + _d(run.calc_lap_rebar_lb)
        )
        wall_side = (
            wall_cy * _mix_price(db, run.mix_design_id) * taxed
            + wall_steel * rebar_cost * taxed
            + wall_steel / Decimal("2000") * tie_rate
            + _d(run.calc_form_ff) * (
                r("forming", "labor_forming_sf", "3.5")
                + r("place_finish", "labor_place_finish_sf", "3.5")
                + r("wreck", "labor_wreck_sf", "1")
                + r("rub_patch", "labor_rub_patch_sf", "0.25")
            )
            + _d(run.calc_backfill_cy) * r("backfill", "labor_backfill_cy", "8")
            + _d(run.calc_drain_lf) * r("french_drains", "labor_french_drain_lf", "10")
        )
        attributed.append((ftg + wall_side).quantize(_Q2))

    # What is left of a row after the attributed pieces — supervision,
    # equipment, the forming package, pumping, fuel — split between the two
    # halves by that row's own form feet against its own footing SF.
    #
    # It has to be the ROW's leftover, not a section pool re-allocated on a
    # different basis. The row's cost was allocated by form feet; pooling at
    # the section and re-splitting by (FF + footing SF) hands a long, short
    # wall more pool than its cost ever received, and the wall — which takes
    # the remainder — silently absorbs the mismatch. That read as a wall rate
    # swinging $15.98 to $35.13 across sixteen identically-built walls.
    margin = _d(getattr(section, "margin_pct", 0)) + _d(getattr(section, "contingency_pct", 0))
    factor = Decimal("1") + margin

    for run, ftg_base, attrib in zip(runs, footing_direct, attributed):
        ff = _d(run.calc_form_ff)
        ftg_sf = _d(run.calc_footing_sf)
        denom = ff + ftg_sf
        cost = _d(run.calc_cost)

        leftover = cost - attrib
        ftg_pool = (leftover * ftg_sf / denom).quantize(_Q2) if denom > 0 else Decimal("0")
        footing = (ftg_base + ftg_pool).quantize(_Q2)
        # Never let the footing exceed the row — a wall with no footing at all
        # should read zero here, not a negative wall.
        if footing > cost:
            footing = cost
        if footing < 0:
            footing = Decimal("0")
        wall = (cost - footing).quantize(_Q2)

        # Sale takes the same remainder rule as cost: round the footing, give
        # the wall what is left of the row's own sale. Rounding both halves
        # independently leaves them a cent short of it.
        sale = _d(run.calc_sale)
        footing_sale = (footing * factor).quantize(_Q2)
        if footing_sale > sale:
            footing_sale = sale

        run.calc_footing_cost = footing
        run.calc_wall_cost = wall
        run.calc_footing_sale = footing_sale
        run.calc_wall_sale = (sale - footing_sale).quantize(_Q2)
        run.calc_wall_cost_per_ff = (wall / ff).quantize(_Q4) if ff > 0 else None
        run.calc_wall_sale_per_ff = (
            (_d(run.calc_wall_sale) / ff).quantize(_Q4) if ff > 0 else None
        )
        run.calc_footing_cost_per_sf = (
            (footing / ftg_sf).quantize(_Q4) if ftg_sf > 0 else None
        )
        run.calc_footing_sale_per_sf = (
            (footing_sale / ftg_sf).quantize(_Q4) if ftg_sf > 0 else None
        )


def _mix_price(db: Session, mix_id: int | None) -> Decimal:
    from app.services.costing import _mix_unit_cost, _z

    # Zero for the split's arithmetic only. The section's unpriced list
    # (costing.section_unpriced) is what says a mix had no price.
    return _z(_mix_unit_cost(db, mix_id))


def _rebar_price(db: Session, kind: str | None) -> Decimal:
    """
    What a pound of bar costs this section — a rebar quote included, since the
    split has to follow the money the section actually carries.
    """
    from app.services import quotes as qt
    from app.services.costing import _rebar_unit_cost, _z

    return _z(_rebar_unit_cost(db, False, kind))
