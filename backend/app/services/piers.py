"""
The pier cage: concrete, steel, and what it costs to drill the hole.

Source: 01-Piers, re-derived in docs/specs/piers-spec.md. Three things here differ
from the workbook on purpose, and all three were asked for:

  * every tie hoop carries a hook or lap, which the sheet's bare circumference
    does not — the same allowance sql/023 already makes for grade beam stirrups
  * a confinement band of closer ties at the top, which the sheet has no field
    for at all
  * real pi and the ASTM bar_weights table, rather than 3.1412 and
    (size/16)^2 x 10.680159

Together they add 2.8% to LBJ's pier steel. Everything else matches.

Two things deliberately kept as the sheet has them: the vertical bars run the
full hole depth (Chad's cages are cut to length and field tied, so there is no
lap to carry and no bottom cover to deduct), and the projection up into the cap
is the DOWELS line, which is what it always was.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.estimate_section import PIER_KINDS, EstimateSection
from app.models.pier_group import PierGroup
from app.services.calc import _rate_numeric, _waste
from app.services.costing import allocate_amount
from app.services.price_book import for_section, priced_as, require_book

_Q3 = Decimal("0.001")
_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")

PI = Decimal(str(math.pi))


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


def tie_count(
    depth_ft: Decimal,
    spacing_in: Decimal | None,
    band_count: int | None = 0,
    band_spacing_in: Decimal | None = None,
) -> Decimal:
    """
    Ties in one pier: the confinement band at the top, then the rest of the
    hole at the running spacing.

        band_count  +  (depth - band_depth) x 12 / spacing

    The band is a COUNT at a spacing, because that is how a drawing says it —
    "3 #3 stirrups at 3 inches top". Its own depth comes off the run below so
    the top few inches are not counted twice.
    """
    depth = _d(depth_ft)
    if depth <= 0:
        return Decimal("0")

    band_n = Decimal(int(band_count or 0))
    band_sp = _d(band_spacing_in)
    band_depth = (band_n * band_sp / Decimal("12")) if band_n > 0 and band_sp > 0 else Decimal("0")
    band_depth = min(band_depth, depth)

    running = Decimal("0")
    sp = _d(spacing_in)
    if sp > 0:
        running = (depth - band_depth) * Decimal("12") / sp
    return (band_n + running).quantize(_Q3)


def hoop_length_ft(diameter_in: Decimal, cover_in: Decimal, hook_in: Decimal) -> Decimal:
    """
    One tie hoop, in feet: the circle inside the cover, plus its hook or lap.

    The workbook writes this as `(dia - 3) x 3.1412` and then multiplies by
    `depth_ft / spacing_in`, which looks like a units error and is not — the
    /12 that would turn inches into feet and the x12 that would turn feet of
    depth into inches of spacing cancel exactly. Verified to the digit on the
    46-pier group. It is written honestly here so nobody has to rediscover that.
    """
    dia = _d(diameter_in) - Decimal("2") * _d(cover_in)
    if dia <= 0:
        return Decimal("0")
    return ((dia * PI + _d(hook_in)) / Decimal("12")).quantize(Decimal("0.000001"))


def shaft_cy(diameter_in: Decimal, depth_ft: Decimal) -> Decimal:
    """A cylinder: pi x (D/12)^2 / 4 x depth / 27."""
    d_ft = _d(diameter_in) / Decimal("12")
    if d_ft <= 0 or _d(depth_ft) <= 0:
        return Decimal("0")
    return (PI * d_ft * d_ft / Decimal("4") * _d(depth_ft) / Decimal("27"))


def bell_cy(diameter_in: Decimal, bell_in: Decimal | None) -> Decimal:
    """
    The bell, as the sheet models it: half the difference between a
    bell-diameter cylinder and a shaft-diameter cylinder, over a height taken
    as the bell diameter in inches read as feet.

    That is a cone approximation and the height convention is the sheet's, not
    a standard. It is untested against a real number — every LBJ pier is
    straight-shafted — so treat the first belled job as a thing to check rather
    than a thing to trust.
    """
    bell = _d(bell_in)
    if bell <= 0:
        return Decimal("0")
    height_ft = bell / Decimal("12")
    return (shaft_cy(bell, height_ft) - shaft_cy(diameter_in, height_ft)) / Decimal("2")


def drill_rate(db: Session, diameter_in: Decimal) -> Decimal | None:
    """
    $/LF to drill this diameter, from pier_drill_rates.

    None when the table has no row for the diameter. The caller surfaces that
    rather than guessing: an interpolated drilling rate across 2,348 LF is a
    five-figure error with nothing on screen to notice.
    """
    # This job's sheet first (sql/050). A sheeted estimate prices ONLY from
    # its sheet — a diameter it has no row for is unpriced, and reports
    # itself the same way a diameter missing from the table always has.
    book = require_book(f"drill rate {_d(diameter_in)}\"")
    if book.has_sheet:
        return book.drill_rate(diameter_in)
    row = db.execute(
        text("SELECT drill_per_lf FROM pier_drill_rates WHERE diameter_in = :d"),
        {"d": _d(diameter_in)},
    ).scalar()
    return _d(row) if row is not None else None


def _estimate_id_of(db: Session, section_id: Any):
    return db.execute(
        text("SELECT estimate_id FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}
    ).scalar()


def _estimate_of_groups(db: Session, groups: list[PierGroup]):
    return _estimate_id_of(db, groups[0].section_id) if groups else None


def refresh_pier_group_calcs(
    db: Session, group: PierGroup, section: EstimateSection | None = None
) -> PierGroup:
    """Populate group.calc_* from the cage schedule. Caller commits.
    A price gate (sql/050): the drilling rate comes off the estimate's sheet."""
    if section is None:
        section = db.get(EstimateSection, group.section_id)
    if section is None:
        raise ValueError("section not found for pier group")
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _refresh_pier_group_calcs(db, group, section)


def _refresh_pier_group_calcs(
    db: Session, group: PierGroup, section: EstimateSection
) -> PierGroup:

    kind = getattr(section, "kind", None)
    waste_c = _waste(section, db, "waste_concrete", "waste_concrete")
    waste_r = _waste(section, db, "waste_rebar", "waste_rebar")
    cover = _rate_numeric(db, kind, "pier_cover_in", Decimal("1.5"))
    hook = _rate_numeric(db, kind, "pier_tie_hook_in", Decimal("0"))
    bottom_cover_in = _rate_numeric(db, kind, "pier_bottom_cover_in", Decimal("0"))

    qty = Decimal(int(group.qty or 0))
    depth = (_d(group.base_depth_ft) + _d(group.rock_penetration_ft)).quantize(_Q3)
    group.calc_total_depth_ft = depth
    group.calc_total_lf = (qty * depth).quantize(_Q3)

    # ---------------------------------------------------------- concrete ----
    shaft = shaft_cy(group.diameter_in, depth)
    bell = bell_cy(group.diameter_in, group.bell_size_in)
    group.calc_shaft_concrete_cy = (shaft * qty * (Decimal("1") + waste_c)).quantize(_Q4)
    group.calc_bell_concrete_cy = (bell * qty * (Decimal("1") + waste_c)).quantize(_Q4)
    group.calc_concrete_cy = (
        _d(group.calc_shaft_concrete_cy) + _d(group.calc_bell_concrete_cy)
    ).quantize(_Q4)

    # ------------------------------------------------------------- steel ----
    # Vertical bars are cut to length: no lap, and no bottom cover unless the
    # assembly says otherwise. waste_rebar here is genuinely waste — drops and
    # mis-cuts — where on a slab mat the same column carries the lap.
    bar_len = depth - _d(bottom_cover_in) / Decimal("12")
    if bar_len < 0:
        bar_len = Decimal("0")
    vert = (
        Decimal(int(group.vert_bars_count or 0))
        * bar_lb_per_ft(db, group.vert_bars_size)
        * bar_len
        * qty
    )

    ties = tie_count(depth, group.tie_spacing_in, group.band_tie_count, group.band_spacing_in)
    group.calc_tie_count = ties
    tie_lb = (
        ties
        * bar_lb_per_ft(db, group.tie_size)
        * hoop_length_ft(group.diameter_in, cover, hook)
        * qty
    )

    dowels = (
        Decimal(int(group.dowels_count or 0))
        * bar_lb_per_ft(db, group.dowels_size)
        * _d(group.dowels_length_ft)
        * qty
    )

    factor = Decimal("1") + waste_r
    group.calc_vert_rebar_lb = (vert * factor).quantize(_Q3)
    group.calc_tie_rebar_lb = (tie_lb * factor).quantize(_Q3)
    group.calc_dowel_rebar_lb = (dowels * factor).quantize(_Q3)
    group.calc_total_rebar_lb = (
        _d(group.calc_vert_rebar_lb)
        + _d(group.calc_tie_rebar_lb)
        + _d(group.calc_dowel_rebar_lb)
    ).quantize(_Q3)

    # ---------------------------------------------------------- drilling ----
    rate = drill_rate(db, group.diameter_in)
    group.calc_drill_lf_rate = rate
    group.calc_drill_cost = (
        (_d(rate) * _d(group.calc_total_lf)).quantize(_Q2) if rate is not None else None
    )

    return group


def drill_quote(
    section: EstimateSection | None, db: Session | None = None
) -> Decimal | None:
    """
    The lump-sum drilling quote governing this section, or None.

    Since sql/039 this lives in `section_quotes` alongside the rebar and PT
    quotes rather than in columns of its own — one mechanism, one staleness
    rule, one place to look. A zero is a cleared field rather than free
    drilling; QuoteSet drops it on the way in.

    Only a piers section can have one.
    """
    if section is None or getattr(section, "kind", None) not in PIER_KINDS:
        return None
    if db is None:
        return None
    from app.services import quotes as qt

    q = qt.load_quotes(db, section.id).get(qt.DRILLING)
    return q.amount if q is not None else None


def _shaped_weight(db: Session, group: PierGroup) -> Decimal | None:
    """
    What the rate table would charge this group — the weight used to apportion a
    lump-sum quote. None when the diameter has no row, which drops the whole
    section back to a flat LF split rather than silently zero-weighting a group
    and handing its drilling to the others.
    """
    rate = drill_rate(db, group.diameter_in)
    if rate is None:
        return None
    return rate * _d(group.calc_total_lf)


def drill_quote_basis(db: Session, groups: list[PierGroup]) -> str:
    """Which apportionment apply_drill_quote will use. Reported, not guessed at."""
    # No `for_section` here: these two read the DRILLING table, not
    # `_rate_numeric`, so there is no section rate to resolve. Claiming a
    # section would be a lie about what the pass is doing.
    with priced_as(db, _estimate_of_groups(db, groups)):
        shaped = [_shaped_weight(db, g) for g in groups]
    if all(w is not None for w in shaped) and sum(shaped, Decimal("0")) > 0:
        return "rate_shape"
    return "lf"


def apply_drill_quote(
    db: Session, section: EstimateSection, groups: list[PierGroup]
) -> Decimal | None:
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _apply_drill_quote(db, section, groups)


def _apply_drill_quote(
    db: Session, section: EstimateSection, groups: list[PierGroup]
) -> Decimal | None:
    """
    Spread a lump-sum drilling quote across the groups by drilled LF.

    The sheet's J54 just replaces the total. That is not enough here, because
    piers allocate everything else on an EA basis and each group carries its own
    cost per pier — drop the whole lump on the section and every per-pier number
    below it is wrong.

    The basis matters as much as the split. Spreading evenly by LF looks
    reasonable and is not: the rate table charges $8/LF for a 24" shaft and
    $30/LF for a 42" one, so a flat per-foot share makes small piers nearly
    three times their real cost and large ones a bargain. A driller's lump sum
    is priced off a mix of diameters, so the honest apportionment is the SHAPE
    of that mix — each group's rate × LF as a fraction of the table's total.
    The quote sets the level; the table sets the relative weights.

    Plain LF is the fallback for when the table cannot describe the shape
    (a diameter with no row), which is a cruder split but a defensible one,
    and totals reports which basis was used rather than leaving you to guess.

    allocate_amount guarantees the shares sum to the quote to the cent.

    calc_drill_lf_rate becomes the EFFECTIVE $/LF under a quote — the share
    divided by that group's feet — so the grid keeps showing a rate you can
    sanity-check against the table it replaced.

    A quote also rescues a diameter the rate table has never heard of: the
    table's job is to guess until a real number arrives, and once one has, a
    missing row is no longer a hole. Returns the quote applied, or None.
    """
    quote = drill_quote(section, db)
    if quote is None:
        return None

    shaped = [_shaped_weight(db, g) for g in groups]
    if all(w is not None for w in shaped) and sum(shaped, Decimal("0")) > 0:
        weights = [w for w in shaped]
    else:
        weights = [_d(g.calc_total_lf) for g in groups]
    shares = allocate_amount(quote, weights)
    for group, share in zip(groups, shares):
        lf = _d(group.calc_total_lf)
        group.calc_drill_cost = share
        group.calc_drill_lf_rate = (share / lf).quantize(_Q4) if lf > 0 else None
    return quote


def rate_table_drill_cost(db: Session, groups: list[PierGroup]) -> Decimal | None:
    """
    What pier_drill_rates would charge for these groups — the comparison shown
    next to a quote. None when any group's diameter has no row, because a
    partial total invites subtracting it from the quote and calling the
    difference a saving.
    """
    total = Decimal("0")
    # No `for_section` here: these two read the DRILLING table, not
    # `_rate_numeric`, so there is no section rate to resolve. Claiming a
    # section would be a lie about what the pass is doing.
    with priced_as(db, _estimate_of_groups(db, groups)):
        for g in groups:
            rate = drill_rate(db, g.diameter_in)
            if rate is None:
                return None
            total += rate * _d(g.calc_total_lf)
    return total.quantize(_Q2)


def refresh_section_pier_calcs(db: Session, section: EstimateSection) -> int:
    """
    Re-run every group in a section; returns the count. Caller commits.

    The quote is applied here rather than in refresh_pier_group_calcs because
    apportioning by LF needs every group's feet at once — a per-group refresh
    cannot know its own share.
    """
    groups = list(
        db.scalars(
            select(PierGroup)
            .where(PierGroup.section_id == section.id)
            .order_by(PierGroup.sort_order, PierGroup.created_at)
        ).all()
    )
    for group in groups:
        refresh_pier_group_calcs(db, group, section)
    apply_drill_quote(db, section, groups)
    return len(groups)


def section_pier_totals(db: Session, section_id: Any) -> dict[str, Any]:
    """Rollup for a piers section. Mirrors calc.section_mono_totals."""
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS group_count,
              coalesce(sum(qty), 0)::int AS pier_count,
              coalesce(sum(calc_total_lf), 0) AS total_lf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_shaft_concrete_cy), 0) AS total_shaft_concrete_cy,
              coalesce(sum(calc_bell_concrete_cy), 0) AS total_bell_concrete_cy,
              coalesce(sum(calc_vert_rebar_lb), 0) AS total_vert_rebar_lb,
              coalesce(sum(calc_tie_rebar_lb), 0) AS total_tie_rebar_lb,
              coalesce(sum(calc_dowel_rebar_lb), 0) AS total_dowel_rebar_lb,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_tie_count * qty), 0) AS total_tie_count,
              coalesce(sum(calc_drill_cost), 0) AS total_drill_cost,
              count(*) FILTER (WHERE calc_drill_lf_rate IS NULL)::int AS groups_without_drill_rate,
              coalesce(sum(calc_direct_cost), 0) AS total_direct_cost,
              coalesce(sum(calc_allocated_cost), 0) AS total_allocated_cost,
              coalesce(sum(calc_equip_fuel), 0) AS total_equip_fuel,
              coalesce(sum(calc_tax), 0) AS total_tax,
              coalesce(sum(calc_cost), 0) AS total_cost,
              coalesce(sum(calc_sale), 0) AS total_sale
            FROM pier_groups
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    out = dict(row)
    n = Decimal(int(out.get("pier_count") or 0))
    cost = _d(out.get("total_cost"))
    sale = _d(out.get("total_sale"))
    out["total_cost_per_unit"] = (cost / n).quantize(_Q4) if n > 0 else None
    out["total_sale_per_unit"] = (sale / n).quantize(_Q4) if n > 0 else None

    # ------------------------------------------------------ drilling source ----
    # Which number priced the biggest line on the job, and — if it was a quote —
    # everything needed to distrust it: what it was priced against, what the
    # takeoff says now, and what the rate table would have charged instead.
    from app.services import quotes as qt

    section = db.get(EstimateSection, section_id)
    q = qt.load_quotes(db, section_id).get(qt.DRILLING) if section is not None else None
    quote = q.amount if q is not None and section.kind in PIER_KINDS else None
    out["drill_source"] = "quote" if quote is not None else "rates"
    out["drill_quote"] = quote
    out["drill_quote_note"] = q.note if quote is not None else None
    out["drill_quote_lf"] = None
    out["drill_quote_stale"] = False
    out["drill_rate_cost"] = None
    out["drill_quote_basis"] = None
    if quote is not None:
        current_lf = _d(out.get("total_lf"))
        out["drill_quote_lf"] = q.baseline_qty
        # An unstamped quote has no baseline to compare against. That is not
        # proof it is current, so it reads as stale rather than as fine.
        out["drill_quote_stale"] = qt.is_stale(q, current_lf)
        groups = list(
            db.scalars(select(PierGroup).where(PierGroup.section_id == section_id)).all()
        )
        out["drill_rate_cost"] = rate_table_drill_cost(db, groups)
        out["drill_quote_basis"] = drill_quote_basis(db, groups)
    return out
