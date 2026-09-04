"""
Quotes — a real number from a supplier, replacing one the app computed.

Three kinds so far, all material:

    drilling   the driller's price for the holes        piers
    rebar      the fabricator's price for the steel     any assembly with bar
    pt         the PT sub's price for the package       mono slab

Two shapes, and the difference runs through everything below:

  * a LUMP ("$54,500 for the drilling") is priced against a takeoff that can
    move underneath it. It has to be spread across the section's rows, its
    baseline has to be stamped, and it can go STALE.

  * a UNIT PRICE ("$1,240/ton delivered") replaces a catalog rate and cannot go
    stale — more tons costs more money, automatically. Nothing to stamp,
    nothing to warn about. Warning anyway would train people to ignore the
    banner that does matter.

**Quotes are material only.** A rebar quote does not touch the TIE STEEL labor
line; a PT quote does not touch placing labor. That was Chad's call and it is
the safe direction: leaving labor in when a quote covered it overstates the bid,
which somebody notices, where suppressing labor that the quote did not cover
understates it, which nobody notices until the job is running. If a
furnish-and-install quote ever needs modelling it should be an explicit flag on
the row, not an assumption made here — and the note field is where the scope
lives until then.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.estimate_section import (
    COLUMN_KINDS,
    DECK_KINDS,
    PAVING_KINDS,
    PIER_KINDS,
    WALL_KINDS,
    EstimateSection,
)
from app.models.section_quote import SectionQuote

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")

# Which assemblies can carry which quote, and what a lump is measured against.
#
# The driver is not decoration: it is the weight a lump is spread by, and the
# quantity its baseline is stamped from. Get it wrong and the money lands on
# the wrong rows.
DRILLING = "drilling"
REBAR = "rebar"
PT = "pt"

STEEL_KINDS = (
    frozenset({"mono_slab", "piers"})
    | PAVING_KINDS | WALL_KINDS | COLUMN_KINDS | DECK_KINDS
)

QUOTE_KINDS: dict[str, dict[str, Any]] = {
    DRILLING: {
        "label": "Drilling",
        "kinds": PIER_KINDS,
        "units": ("LS",),
        "driver": "LF",
        "blurb": "The driller's price for the holes. Replaces the $/LF rate table.",
    },
    REBAR: {
        "label": "Rebar",
        "kinds": STEEL_KINDS,
        # Fabricators quote both ways, so both are accepted rather than
        # converted on a napkin.
        "units": ("LS", "TON", "CWT", "LB"),
        "driver": "LB",
        "blurb": "The fabricator's price for the steel. Material only — TIE STEEL labor still bills.",
    },
    PT: {
        "label": "Post-tension",
        # The CIP deck sheet already has the slot: `N80 = IF(I80 = 0,
        # SF x 1.45, I80)` is a supplier quote replacing the computed figure.
        # That is what this is, so PT on a deck is a quote row and not a
        # thirteenth column (sql/052).
        "kinds": frozenset({"mono_slab"}) | DECK_KINDS,
        "units": ("LS", "SF"),
        "driver": "SF",
        "blurb": "The PT sub's price for the package. Spread across the PT pours only.",
    },
}

# lb in a ton and in a hundredweight. Named rather than inline, because a wrong
# constant here is a 20x error that still looks like a plausible price.
LB_PER_TON = Decimal("2000")
LB_PER_CWT = Decimal("100")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return x if isinstance(x, Decimal) else Decimal(str(x))


def kinds_for(section_kind: str | None) -> list[str]:
    """Which quote kinds this assembly can carry. Drives the UI and validation."""
    return [k for k, spec in QUOTE_KINDS.items() if section_kind in spec["kinds"]]


def units_for(quote_kind: str) -> tuple[str, ...]:
    return QUOTE_KINDS.get(quote_kind, {}).get("units", ("LS",))


@dataclass(frozen=True)
class Quote:
    kind: str
    amount: Decimal
    unit: str
    baseline_qty: Decimal | None
    note: str | None

    @property
    def is_lump(self) -> bool:
        return self.unit == "LS"

    def per_lb(self) -> Decimal | None:
        """
        A rebar quote as $/lb, or None if it is a lump.

        The conversions are the whole reason the unit is stored rather than
        normalised on the way in: a fabricator's paper says $/cwt, and an
        estimator checking this screen against that paper needs to see the
        number they were quoted, not one we divided.
        """
        if self.unit == "LB":
            return self.amount
        if self.unit == "CWT":
            return (self.amount / LB_PER_CWT).quantize(Decimal("0.000001"))
        if self.unit == "TON":
            return (self.amount / LB_PER_TON).quantize(Decimal("0.000001"))
        return None

    def per_sf(self) -> Decimal | None:
        """A PT quote as $/SF, or None if it is a lump."""
        return self.amount if self.unit == "SF" else None


class QuoteSet:
    """
    Every quote on one section, resolved once and passed down.

    Built once per costing pass rather than queried per pour — pricing 25 pours
    should not mean 75 round trips, and more importantly every row in a section
    must price off the same quote.
    """

    def __init__(self, rows: list[SectionQuote] | None = None):
        self._by_kind: dict[str, Quote] = {}
        for r in rows or []:
            amount = _d(r.amount)
            # A zero quote is a cleared field, not a free package. Nobody
            # fabricates 73,000 lb of steel for nothing, so a 0 falls back to
            # the catalog rather than pricing the material at nothing.
            if amount <= 0:
                continue
            self._by_kind[r.kind] = Quote(
                kind=r.kind,
                amount=amount,
                unit=r.unit or "LS",
                baseline_qty=_d(r.baseline_qty) if r.baseline_qty is not None else None,
                note=r.note,
            )

    def get(self, kind: str) -> Quote | None:
        return self._by_kind.get(kind)

    def __bool__(self) -> bool:
        return bool(self._by_kind)

    @property
    def kinds(self) -> list[str]:
        return sorted(self._by_kind)


EMPTY = QuoteSet()


def load_quotes(db: Session, section_id: Any) -> QuoteSet:
    rows = list(
        db.scalars(select(SectionQuote).where(SectionQuote.section_id == section_id)).all()
    )
    return QuoteSet(rows)


# The driver each quote kind is priced against, as a function of ONE takeoff
# row — whatever shape that row is.
#
# This map is the single definition, used by `section_driver_qty` below to stamp
# and check a baseline, and by `costing._apply_lump_quotes` to spread a lump.
# Those two had separate implementations until 2026-09-02 and they disagreed:
# the spread was kind-dispatched through `cost_units` and correct everywhere,
# while the baseline hard-coded `MonoSlab` for every non-pier section. Walls
# keep their takeoff in `wall_runs` and columns in `column_types`, so both
# stamped a baseline of ZERO against 33,728 lb and 47,417 lb of real steel.
#
# The consequence was not a wrong number on screen — it was the removal of the
# check that catches wrong numbers. `is_stale` compared 0 to 0 and returned
# False forever; doubling a wall takeoff left the quote reading "current". A
# $1.00 lump wiped $20,079.95 of wall steel behind a green badge.
#
# That is the $0.65 LS bug — which cost $14,252.58 on the slab and was caught
# ONLY because its badge went stale — with the alarm disconnected. One map, so
# a new assembly cannot be added to one half and forgotten in the other.
LUMP_DRIVERS = {
    REBAR: lambda row: _d(getattr(row, "calc_total_rebar_lb", 0)),
    # PT SF, not section SF. A lump PT quote priced against the whole slab area
    # when only half of it is post-tensioned is a different number.
    # A deck level stores its PT area outright (`calc_pt_sf`, zero when the
    # level carries no cable); a slab pour stores an area and a flag. Same
    # question, two takeoff shapes.
    PT: lambda row: (
        _d(getattr(row, "calc_pt_sf", None))
        if getattr(row, "calc_pt_sf", None) is not None
        else (
            _d(getattr(row, "square_footage", 0))
            if getattr(row, "post_tension", False)
            else Decimal("0")
        )
    ),
    DRILLING: lambda row: _d(getattr(row, "calc_total_lf", 0)),
}


def section_driver_qty(db: Session, section: EstimateSection, quote_kind: str) -> Decimal:
    """
    The takeoff quantity a quote of this kind is priced against — what its
    baseline is stamped from, and what the staleness check compares.

    Computed from `cost_units`, the same rows costing spreads a lump across, so
    the baseline and the spread cannot disagree about what the takeoff is. That
    was always the intent; before 2026-09-02 it was only a comment.
    """
    from app.services.costing import cost_units

    driver = LUMP_DRIVERS.get(quote_kind)
    if driver is None:
        return Decimal("0")

    return sum(
        (driver(u.row) for u in cost_units(db, section)), Decimal("0")
    ).quantize(Decimal("0.001"))


# How far from the catalog a quote may sit before the card warns.
#
# Chad's call, 2026-09-02, deliberately LOOSE: this fires on decimal-point and
# unit mistakes — a lump typed as a rate, $/ton entered as $/lb — and stays
# quiet on a real quote. A badge that fires on every good buy is a badge people
# learn to ignore, and an ignored badge is worse than none because it looks like
# cover.
#
# Overridable per assembly via assembly_rates, then system_settings (sql/046).
WARN_LOW_RATIO = Decimal("0.25")
WARN_HIGH_RATIO = Decimal("4")


def quoted_total(quote: Quote, driver_qty: Decimal) -> Decimal:
    """
    What this quote actually charges for the package, lump or unit-priced.

    A unit price needs the takeoff to become money, which is the reason the
    comparison covers both: `$6.50/LB` instead of `$0.65/LB` is a decimal-point
    error exactly like a mistyped lump, and until now nothing looked at either.
    """
    if quote.is_lump:
        return _d(quote.amount).quantize(_Q2)
    per_unit = quote.per_lb() if quote.kind == REBAR else quote.per_sf()
    if per_unit is None:
        return _d(quote.amount).quantize(_Q2)
    return (per_unit * _d(driver_qty)).quantize(_Q2)


def compare_to_catalog(
    db: Session,
    section: EstimateSection,
    quote: Quote | None,
    driver_qty: Decimal,
) -> dict[str, Any]:
    """
    Quote against catalog: the number, the ratio, and whether to warn.

    ## Why this exists

    Staleness catches a quote whose TAKEOFF moved. Nothing caught a quote that
    was wrong the moment it was typed. On 2026-09-01 a rebar quote entered as
    `$0.65 LS` — sixty-five cents, lump, against 21,945 lb — understated the
    mono slab by $14,252.58 and sat behind a green "current" badge. The catalog
    said $14,263 for that same steel. Nothing put those two numbers side by side.

    Drilling has had this comparison since piers were built
    (`rate_table_drill_cost`), and it is the reason a bad drilling number was
    always visible on its own terms. This gives rebar and PT the same thing.

    ## What it is not

    It does not refuse anything. Chad, offered a hard validation on 2026-09-01,
    said "Skip it" — and he was right: a sub's real price is sometimes a third
    of catalog, and an estimator who cannot enter what he was quoted will keep
    the number somewhere the app cannot see it. The comparison is always shown;
    only the badge is conditional.
    """
    out: dict[str, Any] = {
        "catalog_total": None,
        "quoted_total": None,
        "catalog_ratio": None,
        "catalog_verdict": None,
    }
    if quote is None:
        return out

    from app.services.calc import _rate_numeric
    from app.services.costing import catalog_cost_for_quote

    kind = getattr(section, "kind", None)
    low = _rate_numeric(db, kind, "quote_warn_low_ratio", WARN_LOW_RATIO)
    high = _rate_numeric(db, kind, "quote_warn_high_ratio", WARN_HIGH_RATIO)

    charged = quoted_total(quote, driver_qty)
    out["quoted_total"] = charged

    catalog = catalog_cost_for_quote(db, section, quote.kind)
    if catalog is None or catalog <= 0 or charged <= 0:
        # No honest comparison to draw. Explicitly not a verdict of "ok" —
        # "we could not check this" and "we checked this and it is fine" are
        # different states and the card must not conflate them.
        return out

    out["catalog_total"] = catalog
    # Six places, not four. A $0.65 lump against $13,167 of catalog is
    # 0.0000494, which quantized to 4dp is exactly 0.0000 — the ratio that
    # proves the error rounds away to a number that looks like missing data.
    ratio = (charged / catalog).quantize(Decimal("0.000001"))
    out["catalog_ratio"] = ratio
    out["catalog_verdict"] = (
        "far_below" if ratio < low else "far_above" if ratio > high else "ok"
    )
    return out


def is_stale(quote: Quote | None, current_qty: Decimal) -> bool:
    """
    True when a LUMP was priced against a different takeoff than the one on
    screen — or against none anybody recorded.

    A unit-priced quote is never stale: it follows the takeoff by construction.
    An unstamped lump reads as stale, because having no baseline is not
    evidence of being current.
    """
    if quote is None or not quote.is_lump:
        return False
    if quote.baseline_qty is None:
        return True
    return _d(quote.baseline_qty) != _d(current_qty)


def spread(amount: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """
    Split a lump across rows by weight, to the cent.

    Thin wrapper over costing.allocate_amount so quotes.py does not carry a
    second copy of the remainder rule.
    """
    from app.services.costing import allocate_amount

    return allocate_amount(amount, weights)
