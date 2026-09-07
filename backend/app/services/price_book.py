"""
The estimate price sheet, and the book every costing pass reads from.

docs/specs/estimate-price-sheet-spec.md. Chad, 2026-09-02:

    "I like having a master list of rough mix prices that we get from
    suppliers that we update as we get them, then as we start an estimate, it
    pulls those numbers and we can update when a supplier gives us a quote."

    master list  ──pull──▶  estimate price sheet  ──▶  every section
    (the catalog)                  │
        ▲                     edit per job
        └── drift is DETECTED, never applied

## The three pieces

`PriceBook` — one estimate's sheet, loaded once and read by every price lookup
in a costing pass. The same reason `QuoteSet` exists: pricing 25 pours should
not mean 75 round trips, and every row on a section must price off the same
numbers.

`pull_prices` — copies the master list onto the sheet. New items appear,
unedited rows follow the catalog, **edited rows are never overwritten**, and an
unpriced master item is reported rather than copied as zero (decision 5).

`priced_as` — the context every costing entry point runs inside. This is how
the book reaches ~100 lookups in six files without threading a parameter
through each of them, and — more importantly — how a lookup that was FORGOTTEN
becomes loud instead of silently reading the catalog.

## What is on the sheet (sql/048 + 049)

    mix            mix_designs.unit_cost          by ref_id
    material       materials.unit_cost            by ref_id
    equipment      equipment.unit_cost            by ref_id     ($0 = unpriced)
    setting        system_settings, MONETARY_KEYS by ref_key
    assembly_rate  assembly_rates, MONETARY_KEYS  by (scope=kind, ref_key)
    drill_rate     pier_drill_rates.drill_per_lf  by ref_key = diameter (sql/050)

Rules — waste, divisors, pacing, geometry, the quote band — are RULE_KEYS and
never pulled; `_rate_numeric` reads them live.

## Why a context rather than a parameter

The spec proposed passing the book down like `QuoteSet`. Building it, the
parameter version had exactly the failure the spec warned about: a site I
missed would price from the catalog, quietly, forever. A context established at
the gates — `refresh_pour_costs`, `calc_forming_materials`,
`calc_labor_materials`, `calc_estimate_equipment`, `cost_units`,
`catalog_cost_for_quote`, `section_material_costs`, `tax_rate_for`,
`resolve_vapor_*` — means there is no per-site parameter to forget. `require_book()` then asks the only question that matters: *is a
costing lookup happening outside any book?* In tests that raises. In production
it falls back to the catalog and logs — the behaviour the app had before this
file existed, so nothing gets worse; it just cannot get better silently.

## Once a sheet exists, it is the only source

An estimate with a sheet prices ONLY from its sheet. A catalog item that is
not on the sheet — added after the pull — is unpriced on that job until the
next pull, and the drift check says so. The alternative, "fall back to the
catalog for anything missing", is the spec's *partial freezing* failure: an
estimate 95% pinned that silently drifts on the rest, which is harder to trust
than one that drifts openly.

An estimate with NO sheet (zero rows — created outside the router, or a
fixture that never pulled) prices from the catalog exactly as before sql/048.
"""

from __future__ import annotations

import contextvars
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.estimate_price import EstimatePrice

log = logging.getLogger(__name__)

_Q4 = Decimal("0.0001")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return x if isinstance(x, Decimal) else Decimal(str(x))


# -------------------------------------------------------- price or rule ----
#
# `system_settings` and `assembly_rates` hold PRICES and RULES in the same
# tables, with names that do not tell them apart: `labor_forming_sf` is $/SF
# and `nails_16p_per_sf` is SF per box. A sweep of `LIKE '%_sf'` would freeze
# eight divisors and break every quantity in the app. So the split is
# enumerated by hand, in both directions, and `test_price_sheet_rates.py`
# fails the day a key appears in either table that is on neither list —
# adding a key means deciding what it is.
#
# Monetary keys are PULLED onto the sheet and frozen per job. Rules stay live:
# a correction to how the work is computed must reach an old estimate on
# recalc (spec, "What is a price, and what is a rule").

MONETARY_KEYS: dict[str, tuple[str, str]] = {
    # key: (label, unit)                          $ per …
    # -- company day rates and per-unit labor (system_settings, some overridden per assembly)
    "labor_super_day_rate":      ("Superintendent", "DAY"),
    "labor_foreman_day_rate":    ("Foreman", "DAY"),
    "labor_pm_day_rate":         ("Project manager", "DAY"),
    "labor_expense_day_rate":    ("Field expense", "DAY"),
    "labor_forming_sf":          ("Forming labor", "SF"),
    "labor_place_finish_sf":     ("Place & finish labor", "SF"),
    "labor_place_finish_ea":     ("Place & finish labor", "EA"),
    "labor_wreck_sf":            ("Wreck forms labor", "SF"),
    "labor_grading_sf":          ("Grading labor", "SF"),
    "labor_tie_steel_ton":       ("Tie steel labor", "TON"),
    "labor_rebar_lb":            ("Rebar labor", "LB"),
    "labor_excavation_cy":       ("Excavation labor", "CY"),
    "labor_excavate_cy":         ("Excavate labor", "CY"),
    "labor_backfill_cy":         ("Backfill labor", "CY"),
    "labor_drops_ff":            ("Drops labor", "FF"),
    "labor_hold_down_ea":        ("Hold-downs labor", "EA"),
    "labor_brick_ledge_lf":      ("Brick ledge labor", "LF"),
    "labor_curb_lf":             ("Curb labor", "LF"),
    "labor_footings_sf":         ("Footings labor", "SF"),
    "labor_french_drain_lf":     ("French drain labor", "LF"),
    "labor_build_up_sf":         ("Build-up labor", "SF"),
    "labor_rub_patch_sf":        ("Rub & patch labor", "SF"),
    "labor_layout_ea":           ("Layout labor", "EA"),
    "labor_cleanup_ea":          ("Cleanup labor", "EA"),
    "labor_pier_cap_ea":         ("Pier cap labor", "EA"),
    # -- the elevated deck's own labor (sql/052)
    "labor_reshoring_sf":        ("Reshoring labor", "SF"),
    "labor_edge_rails_lf":       ("Edge & safety rails labor", "LF"),
    "labor_gb_forming_ff":       ("Grade beam forming labor", "FF"),
    "labor_stud_rails_ton":      ("Stud rails labor", "TON"),
    "labor_cable_placement_lb":  ("PT cable placement labor", "LB"),
    # -- equipment day rates that live as rates rather than catalog rows
    "equip_misc_day_rate":       ("Misc equipment", "DAY"),
    "equip_vault_day_rate":      ("Vault", "DAY"),
    "equip_storage_day_rate":    ("Storage", "DAY"),
    "equip_fork_truck_day_rate": ("Fork truck", "DAY"),
    "equip_easy_drill_day_rate": ("Easy drill", "DAY"),
    "equip_bobcat_day_rate":     ("Bobcat", "DAY"),
    "equip_light_tower_day_rate": ("Light tower", "DAY"),
    "equip_skytrack_day_rate":   ("SkyTrack", "DAY"),
    "equip_mini_excavator_day_rate": ("Mini excavator", "DAY"),
    "equip_hoisting_day_rate":   ("Hoisting", "DAY"),
    "equip_skid_steer_day_rate": ("Skid steer", "DAY"),
    "equip_skid_day_rate":       ("Skid steer", "DAY"),
    "equip_trencher_day_rate":   ("Trencher", "DAY"),
    "equip_crane_day_rate":      ("Crane & operator", "DAY"),
    "equip_20_ton_lift_day_rate": ("20 ton lift", "DAY"),
    "out_of_town_day_rate":      ("Out of town", "DAY"),
    # Getting the iron to the job and home again — one round trip (sql/053).
    # The workbook prices it nowhere; this is a real cost the sheets have been
    # leaving out. Deliberately unset company-wide, so it reads as unpriced
    # rather than free until somebody says what a move costs.
    "mobilization_ls":           ("Mobilization", "LS"),
    # The MISCELLANEOUS contract line on piers and walls: the lump a section
    # starts at, quantity 0 until typed. A literal 1000 in the code until
    # sql/065 (audit 2026-09-04, P3).
    "misc_contract_ls":          ("Miscellaneous contract", "LS"),
    # -- contract services and per-unit costs
    "concrete_pump_cy":          ("Concrete pump", "CY"),
    "haul_off_cy":               ("Haul off", "CY"),
    "cure_sf":                   ("Cure", "SF"),
    "saw_cutting_lf":            ("Saw cutting", "LF"),
    "joint_construction_lf":     ("Construction joint", "LF"),
    "joint_control_lf":          ("Control joint", "LF"),
    "joint_soft_cut_lf":         ("Soft-cut joint", "LF"),
    "demo_lf":                   ("Demo", "LF"),
    "stamping_sf":               ("Stamping", "SF"),
    "slip_form_sf":              ("Slip form", "SF"),
    "surveying_ea":              ("Surveying", "EA"),
    "waterproofing_sf":          ("Waterproofing", "SF"),
    "barricades_month":          ("Barricades", "MONTH"),
    "barricades_lf":             ("Barricades", "LF"),
    "engineering_sf":            ("Engineering", "SF"),
    "freight_load":              ("Freight", "LOAD"),
    # -- deck materials priced per unit of DECK rather than per catalog row
    "pt_cable_sf":               ("PT cable", "SF"),
    "stud_rails_lb":             ("Stud rails", "LB"),
    "carton_forms_sf":           ("Carton forms", "SF"),
    "plywood_forming_sf":        ("Plywood forming", "SF"),
    "form_rental_shoring_sf":    ("Form rental shoring", "SF"),
    # Registered but deliberately absent from every table: the deck sheet's
    # F83 is blank, so reshoring material has no price and the section says
    # so rather than costing it at zero (sql/052).
    "reshoring_material_sf":     ("Reshoring material", "SF"),
    "form_rental_contact_ft":    ("Form rental", "CONTACT FT"),
    "rock_cy":                   ("Rock", "CY"),            # on paving/sidewalk; not read by any service (audit P3)
    "sand_unit_cost":            ("Sand", "CY"),            # an assembly override of the SAND material price; no rows today
    # -- the two ratios that only exist to turn quantities into money (spec, judgment calls)
    "sales_tax_pct":             ("Sales tax", "RATIO"),
    "equip_fuel_maint_pct":      ("Fuel & maintenance on rentals", "RATIO"),
}

RULE_KEYS: frozenset[str] = frozenset({
    # waste and allowances
    "waste_concrete", "waste_sand", "waste_poly", "waste_rebar",
    "waste_rebar_beams",
    "support_rebar_lb_per_sf", "pt_lb_per_sf", "labor_tie_steel_free_lb_per_sf",
    # forming quantities and divisors — SF per box, LF per SF, sheets per SF
    "form_percent", "form_waste", "form_rental_percent",
    "nails_16p_per_sf", "nails_8p_per_sf", "lumber_2x4_per_sf", "lumber_ply_per_sf",
    "lumber_2x4_per_ff", "lumber_ply_per_ff", "chairs_sf_per_bag", "form_release_sf_per_gal",
    "patch_sf_per_bag", "stakes_per_column", "chamfer_per_column", "camlocks_per_ff",
    # the elevated deck's divisors, all riding perm edge LF + GB form FF
    "lumber_2x4_per_lf", "lumber_2x6_per_lf", "lumber_2x10_per_lf", "lumber_ply_per_lf",
    "stakes_2x10_lf_per_stake", "stakes_per_bundle", "nails_edge_factor",
    "pavecrete_sf_per_bag", "cure_sf_per_gal", "accessories_stud_rail_factor",
    # the older sets' divisors, on the ladder since 2026-09-06 (audit P3):
    # tie wire per roll of SF, and concrete haul-off loads per CY
    "tie_wire_sf_per_roll", "haul_off_cy_per_load",
    # J83 on the deck sheet is one cell read by two lines; here it is two rules
    "reshoring_multiplier", "form_rental_shoring_multiplier",
    "wall_ties_per_ff", "pipe_brace_per_ff", "horiz_lap_ft_per_course", "sand_in_under_form",
    # supervision pacing
    "labor_super_sf_per_week", "labor_super_days_per_week", "columns_per_super_week",
    # pier geometry
    "pier_cover_in", "pier_bottom_cover_in", "pier_tie_hook_in",
    "pier_band_spacing_in", "pier_band_tie_count",
    # swell, switches, pointers, the quote band
    "haul_off_swell", "backfill_swell", "equip_use_rental_tiers", "vapor_barrier_enabled",
    "default_vapor_barrier_material_id", "default_vapor_tape_material_id",
    "vapor_tape_rolls_per_barrier_roll", "quote_warn_low_ratio", "quote_warn_high_ratio",
})

# The categories the screen groups by. Assembly overrides get their own group
# per assembly so "paving forms at $0.30 against the company's $0.45" reads
# as what it is.
RATE_CATEGORY = "labor & company rates"
EQUIPMENT_CATEGORY = "equipment"
DRILL_CATEGORY = "drilling"


def drill_key(diameter_in: Any) -> str:
    """The sheet key for a shaft diameter: 24.00 and 24 are the same row."""
    d = _d(diameter_in).normalize()
    return format(d, "f")


def rate_label(key: str) -> str:
    return MONETARY_KEYS.get(key, (key, ""))[0]


# ------------------------------------------------------------------ book ----


@dataclass
class PriceBook:
    """One estimate's sheet, keyed the way lookups ask for it."""

    estimate_id: UUID | None
    mixes: dict[int, Decimal] = field(default_factory=dict)
    materials: dict[int, Decimal] = field(default_factory=dict)
    equipment: dict[int, Decimal] = field(default_factory=dict)
    # (scope, key) → value. scope None is the company setting; a scope is an
    # assembly kind's own rate — the same two levels `_rate_numeric` reads.
    rates: dict[tuple[str | None, str], Decimal] = field(default_factory=dict)
    # diameter key → $/LF to drill it (pier_drill_rates.drill_per_lf)
    drill: dict[str, Decimal] = field(default_factory=dict)
    # Row count at load. Zero means "no sheet" → catalog behaviour, not
    # "everything is unpriced".
    rows: int = 0

    @property
    def has_sheet(self) -> bool:
        return self.rows > 0

    def equipment_price(self, equipment_id: int | None) -> Decimal | None:
        if equipment_id is None:
            return None
        return self.equipment.get(int(equipment_id))

    def price_equipment_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        """A catalog equipment row as this job pays for it — see
        `price_material_row`. Absent from a sheeted job = unpriced (None)."""
        if row is None or not self.has_sheet:
            return row
        out = dict(row)
        out["unit_cost"] = self.equipment.get(int(row["id"]))
        out["price_source"] = "sheet" if out["unit_cost"] is not None else None
        return out

    def drill_rate(self, diameter_in: Any) -> Decimal | None:
        """$/LF to drill this diameter on this job, or None — unpriced on a
        sheeted job (a diameter with no row), "ask the table" on an unsheeted one."""
        return self.drill.get(drill_key(diameter_in))

    def rate(self, kind: str | None, key: str) -> Decimal | None:
        """
        A monetary rate as this job pays it: the assembly's own row, else the
        company row, else None — which on a sheeted estimate means "not on the
        sheet; use the code default", exactly where `_rate_numeric` lands when
        neither table has the key.
        """
        if kind is not None:
            v = self.rates.get((kind, key))
            if v is not None:
                return v
        return self.rates.get((None, key))

    def mix_price(self, mix_id: int | None) -> Decimal | None:
        """The sheet's price for a mix, or None — which means UNPRICED on a
        sheeted estimate, and "ask the catalog" on an unsheeted one."""
        if mix_id is None:
            return None
        return self.mixes.get(int(mix_id))

    def material_price(self, material_id: int | None) -> Decimal | None:
        if material_id is None:
            return None
        return self.materials.get(int(material_id))

    def price_material_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        A catalog row as this job pays for it.

        Name resolution still happens against the catalog — the catalog is the
        list of what EXISTS; the sheet is what it COSTS on this job. So the row
        comes in resolved, and only its `unit_cost` is swapped. On a sheeted
        estimate an item absent from the sheet comes back with `unit_cost`
        None: unpriced, per the rule in the module docstring.
        """
        if row is None or not self.has_sheet:
            return row
        out = dict(row)
        out["unit_cost"] = self.materials.get(int(row["id"]))
        out["price_source"] = "sheet" if out["unit_cost"] is not None else None
        return out


NO_BOOK = PriceBook(estimate_id=None)


def load_price_book(db: Session, estimate_id: UUID | None) -> PriceBook:
    if estimate_id is None:
        return NO_BOOK
    book = PriceBook(estimate_id=estimate_id)
    for r in db.execute(
        text(
            "SELECT kind, scope, ref_id, ref_key, value FROM estimate_prices "
            "WHERE estimate_id = :e"
        ),
        {"e": str(estimate_id)},
    ).mappings():
        book.rows += 1
        kind = r["kind"]
        if kind == "mix" and r["ref_id"] is not None:
            book.mixes[int(r["ref_id"])] = _d(r["value"])
        elif kind == "material" and r["ref_id"] is not None:
            book.materials[int(r["ref_id"])] = _d(r["value"])
        elif kind == "equipment" and r["ref_id"] is not None:
            book.equipment[int(r["ref_id"])] = _d(r["value"])
        elif kind == "setting" and r["ref_key"]:
            book.rates[(None, r["ref_key"])] = _d(r["value"])
        elif kind == "assembly_rate" and r["ref_key"]:
            book.rates[(r["scope"], r["ref_key"])] = _d(r["value"])
        elif kind == "drill_rate" and r["ref_key"]:
            book.drill[r["ref_key"]] = _d(r["value"])
    return book


# --------------------------------------------------------------- context ----

_current: contextvars.ContextVar[PriceBook | None] = contextvars.ContextVar(
    "estimating_price_book", default=None
)


class NoPriceBook(RuntimeError):
    """A costing lookup ran outside any `priced_as` context — a site nobody
    threaded the book to. Raised only when ESTIMATING_STRICT_PRICES=1 (tests)."""


def current_book() -> PriceBook | None:
    return _current.get()


# ------------------------------------------- section-level or job-level ----
#
# WHERE a rate is allowed to be set. Chad, 2026-09-04, stating the policy:
#
#     "I want all the rates editable per section, each section should be
#      separate from the others for labor. we have a default that we set when
#      we start then can change as needed when we make it past the first round
#      of proposals. forming labor for slabs, paving, CIP decks, etc is based
#      on that section. materials should be standard across the estimate.
#      concrete and materials are quoted per job so should be edited that way."
#
# So: **labor is a section fact, material is a job fact.**
#
# Most of that was already true and needed no code. Mixes and materials are
# catalog rows on the price sheet (`kind='mix'` / `'material'`, resolved by
# ref_id) and never come through `_rate_numeric` at all, so concrete and
# lumber have always been job-level and could never be set on a section.
#
# The list below is the handful that DO come through here and are materials
# anyway — bought by the square foot or the pound instead of by a catalog row —
# plus the job and company facts that were never section-shaped. Without this,
# the section rates card offered a box for PT cable at $1.45/SF, which is
# $50,384.96 on LBJ, on a section rather than on the job that quoted it.
#
# Everything not named here is SECTION-level: labor, equipment day rates, the
# subbed services, the waste factors and the divisors — all of them things
# that describe this bit of work.

# The line that took two passes to find. The first cut said "a material is a
# material however it is priced" and put PT cable here. Chad, 2026-09-04:
#
#     "PT cables are section level, per sf on slabs is different the decks.
#      also have done one a project that is townhomes and apartments and they
#      had different pt spacing."
#
# Which is the better rule, and it is not about materials at all. What decides
# the level is **what the price is per**:
#
#   * priced per unit of THE WORK — $/SF of slab, $/SF of deck — varies with
#     what is being built, so it is a SECTION rate however material-shaped it
#     looks. PT at $1.45/SF is not the same purchase on a slab as on a deck;
#     `pt_lb_per_sf`, the cable weight, was already a section-level rule for
#     the same reason, which is what lets one job carry townhomes and
#     apartments at different spacings.
#
#   * priced per unit of THE MATERIAL — $/CY of sand, $/lb of steel — is the
#     supplier's number for the job, and it does not care which section the
#     truck backs up to.

ESTIMATE_LEVEL_KEYS: frozenset[str] = frozenset({
    # Priced per unit of the MATERIAL. A supplier quotes these for the job.
    "stud_rails_lb",
    "rock_cy",
    "sand_unit_cost",
    # Job facts. Tax follows the project and the fuel uplift follows the
    # company; neither is a property of one section's work.
    "sales_tax_pct",
    "equip_fuel_maint_pct",
    # Supervision is priced for the job. Chad, 2026-09-05: "supervision,
    # equipment, materials are all project specific pricing.. labor changes
    # with each section." The DAYS stay per section (labor_super_sf_per_week
    # and labor_super_days_per_week are rules, read per kind); the day RATES
    # are the job's.
    "labor_super_day_rate",
    "labor_foreman_day_rate",
    "labor_pm_day_rate",
    "labor_expense_day_rate",
    # WHICH material, so it follows the material.
    "default_vapor_barrier_material_id",
    "default_vapor_tape_material_id",
    # Company conventions. A quote band that differed per section would make
    # the badge meaningless, and the rental tier is how S&S bills, not how
    # this deck is built.
    "quote_warn_low_ratio",
    "quote_warn_high_ratio",
    "equip_use_rental_tiers",
    # Mobilization and the equipment DAY RATES are the job's too. Chad,
    # 2026-09-05, after the first seeding took them per section: "mobilization
    # and the equipment day rates are per job." The machine catalog was
    # already on the job sheet; these are the day rates that live as keys
    # (assembly rates for the machines only one kind uses, and the company's
    # misc/vault). How many DAYS a section needs stays the section's — that
    # is the supervision ladder, a rule.
    "mobilization_ls",
    "equip_misc_day_rate",
    "equip_vault_day_rate",
    "equip_storage_day_rate",
    "equip_fork_truck_day_rate",
    "equip_easy_drill_day_rate",
    "equip_bobcat_day_rate",
    "equip_light_tower_day_rate",
    "equip_skytrack_day_rate",
    "equip_mini_excavator_day_rate",
    "equip_hoisting_day_rate",
    "equip_skid_steer_day_rate",
    "equip_skid_day_rate",
    "equip_trencher_day_rate",
    "equip_crane_day_rate",
    "equip_20_ton_lift_day_rate",
})


def rate_level(key: str) -> str:
    """Where this rate is allowed to be set: "section" or "estimate"."""
    return "estimate" if key in ESTIMATE_LEVEL_KEYS else "section"


# ------------------------------------------------------- the section ----
#
# Which SECTION the current pass is costing (sql/055). A separate context from
# the book, deliberately: the book is one per estimate and is reused across the
# sections under it, while this changes on every gate.
#
# Same reasoning as the book itself, and the same evidence. `_rate_numeric` has
# 113 call sites. Threading a section_id through them would mean 113 chances to
# forget one, and a forgotten one does not fail — it quietly reads the
# company's number for a section that overrode it, forever. A context set at
# the gates cannot be forgotten per-site, because there are no per-site sites.
#
# None means "no section in view" — a catalog read, a quote comparison, a test
# calling a helper bare. Nothing breaks: the ladder simply starts one rung down.

_section: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "estimating_section", default=None
)


def current_section() -> UUID | None:
    return _section.get()


@contextmanager
def for_section(section_id: UUID | None) -> Iterator[None]:
    """Run a pass as one section, so its own rates win. Re-entrant."""
    token = _section.set(section_id)
    try:
        yield
    finally:
        _section.reset(token)


# ----------------------------------------------------- what was read ----
#
# A pass can RECORD which rate keys it looked up. That is how the section's
# rates screen knows what to show: not a hand-written list of "keys a paving
# section reads", which would drift from the line sets the day somebody adds a
# line, but the keys the takeoff actually asked for while it ran.

_recording: contextvars.ContextVar[dict[str, Decimal | None] | None] = (
    contextvars.ContextVar("estimating_rate_reads", default=None)
)


def note_rate_read(key: str, default: Decimal) -> None:
    seen = _recording.get()
    if seen is None or key in seen:
        return
    # `_equip_price` passes Decimal("NaN") as a sentinel meaning "there is no
    # code default — tell me if nothing answered". That is a real default of
    # None, not a number, and letting a NaN out of here 500s the rates screen
    # on a JSON serialiser rather than saying so.
    seen[key] = None if default.is_nan() else default


@contextmanager
def recording_rates() -> Iterator[dict[str, Decimal | None]]:
    """Collect every rate key a pass reads, and the code default behind it."""
    seen: dict[str, Decimal | None] = {}
    token = _recording.set(seen)
    try:
        yield seen
    finally:
        _recording.reset(token)


@contextmanager
def priced_as(db: Session, estimate_id: UUID | None) -> Iterator[PriceBook]:
    """
    Run a costing pass against one estimate's sheet.

    Re-entrant: an inner call for the same estimate reuses the outer book
    rather than reloading it, so `refresh_pour_costs` → `split_wall_and_footing`
    → `_rebar_price` all read one snapshot.
    """
    outer = _current.get()
    if outer is not None and outer.estimate_id == estimate_id:
        yield outer
        return
    book = load_price_book(db, estimate_id)
    token = _current.set(book)
    try:
        yield book
    finally:
        _current.reset(token)


def _strict() -> bool:
    return os.environ.get("ESTIMATING_STRICT_PRICES", "") == "1"


def require_book(what: str) -> PriceBook:
    """
    The book for the current costing pass — or the guard firing.

    Every costing-side price lookup calls this. Outside any context there is no
    estimate to be honest about, so:

      * strict (tests):     raise. The forgotten site is a test failure.
      * production:         catalog behaviour, plus a log line. Nothing gets
                            worse than it was before sql/048; it just cannot
                            silently get better on a job that has a sheet.
    """
    book = _current.get()
    if book is not None:
        return book
    if _strict():
        raise NoPriceBook(
            f"{what} was priced outside any price-book context. Wrap the caller "
            f"in `priced_as(db, estimate_id)` — see services/price_book.py."
        )
    log.warning("price lookup outside a price-book context: %s", what)
    return NO_BOOK


@contextmanager
def catalog_only() -> Iterator[None]:
    """
    Explicitly price from the catalog, for code that is NOT costing an
    estimate — the catalog screens, a drift comparison, a test of name
    resolution. Says so at the call site, so the guard has nothing to catch.
    """
    token = _current.set(NO_BOOK)
    try:
        yield
    finally:
        _current.reset(token)


# ------------------------------------------------------------------ pull ----


@dataclass
class PullResult:
    """What a pull did, or — dry run — what it would do."""

    estimate_id: UUID
    applied: bool
    new: list[dict[str, Any]] = field(default_factory=list)          # not on the sheet before
    changed: list[dict[str, Any]] = field(default_factory=list)      # unedited, catalog moved → followed
    conflicts: list[dict[str, Any]] = field(default_factory=list)    # EDITED, catalog moved → kept yours
    unpriced: list[dict[str, Any]] = field(default_factory=list)     # master has no price → not copied
    retired: list[dict[str, Any]] = field(default_factory=list)      # on the sheet, gone from the master list
    unchanged: int = 0

    @property
    def drift(self) -> int:
        """How many prices on the master list differ from this sheet."""
        return len(self.changed) + len(self.conflicts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimate_id": str(self.estimate_id),
            "applied": self.applied,
            "new": self.new,
            "changed": self.changed,
            "conflicts": self.conflicts,
            "unpriced": self.unpriced,
            "retired": self.retired,
            "unchanged": self.unchanged,
            "drift": self.drift,
        }


def _numeric_or_none(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw).strip().strip('"'))
    except Exception:
        return None


def _master_list(db: Session) -> list[dict[str, Any]]:
    """
    Every priceable item on the master list.

    Stage 1: mixes and materials. Stage 2: equipment, and every MONETARY key
    in `system_settings` (scope None) and `assembly_rates` (scope = the
    assembly kind). Rules are never listed. An equipment row priced at $0 is
    unpriced — `_equip_price` has never accepted a zero as a price.
    """
    out: list[dict[str, Any]] = []
    for r in db.execute(
        text("SELECT id, code, unit, unit_cost FROM mix_designs WHERE is_active ORDER BY sort_order, id")
    ).mappings():
        out.append({"kind": "mix", "scope": None, "ref_id": r["id"], "ref_key": None,
                    "label": r["code"], "unit": r["unit"],
                    "category": "concrete", "catalog_value": r["unit_cost"]})
    for r in db.execute(
        text("SELECT id, name, unit, unit_cost, category FROM materials "
             "WHERE coalesce(is_active, true) ORDER BY sort_order NULLS LAST, id")
    ).mappings():
        out.append({"kind": "material", "scope": None, "ref_id": r["id"], "ref_key": None,
                    "label": r["name"], "unit": r["unit"],
                    "category": r["category"], "catalog_value": r["unit_cost"]})
    for r in db.execute(
        text("SELECT id, name, unit, unit_cost FROM equipment "
             "WHERE is_active ORDER BY sort_order, id")
    ).mappings():
        cost = r["unit_cost"]
        if cost is not None and _d(cost) <= 0:
            cost = None
        out.append({"kind": "equipment", "scope": None, "ref_id": r["id"], "ref_key": None,
                    "label": r["name"], "unit": r["unit"] or "DAY",
                    "category": EQUIPMENT_CATEGORY, "catalog_value": cost})
    for r in db.execute(
        text("SELECT key, value #>> '{}' AS value FROM system_settings ORDER BY key")
    ).mappings():
        if r["key"] not in MONETARY_KEYS:
            continue
        label, unit = MONETARY_KEYS[r["key"]]
        out.append({"kind": "setting", "scope": None, "ref_id": None, "ref_key": r["key"],
                    "label": label, "unit": unit, "category": RATE_CATEGORY,
                    "catalog_value": _numeric_or_none(r["value"])})
    for r in db.execute(
        text("SELECT kind, key, value FROM assembly_rates ORDER BY kind, key")
    ).mappings():
        if r["key"] not in MONETARY_KEYS:
            continue
        label, unit = MONETARY_KEYS[r["key"]]
        out.append({"kind": "assembly_rate", "scope": r["kind"], "ref_id": None, "ref_key": r["key"],
                    "label": label, "unit": unit, "category": f"{r['kind']} rates",
                    "catalog_value": _numeric_or_none(r["value"])})
    # Stage 4: drilling, by shaft diameter. Only drill_per_lf is read by the
    # app; casing and deduct columns are reference data and stay in the table.
    for r in db.execute(
        text("SELECT diameter_in, drill_per_lf FROM pier_drill_rates ORDER BY diameter_in")
    ).mappings():
        cost = r["drill_per_lf"]
        if cost is not None and _d(cost) <= 0:
            cost = None
        key = drill_key(r["diameter_in"])
        out.append({"kind": "drill_rate", "scope": None, "ref_id": None, "ref_key": key,
                    "label": f'Drilling {key}" shaft', "unit": "LF",
                    "category": DRILL_CATEGORY, "catalog_value": cost})
    return out


def _key(kind: str, scope: str | None, ref_id: int | None, ref_key: str | None) -> tuple:
    """The sheet's unique key — mirrors estimate_prices_uidx."""
    return (kind, scope or "", ref_key if ref_key else (int(ref_id) if ref_id is not None else None))


def pull_prices(db: Session, estimate_id: UUID, *, apply: bool = True) -> PullResult:
    """
    Copy the master list onto this estimate's sheet.

    The rules, each of which is a test in tests/test_price_sheet.py:

      new         master item not on the sheet → added at the master price
      changed     on the sheet, NOT edited, master moved → follows the master
      conflict    on the sheet, EDITED, master moved → **yours is kept**; the
                  catalog_value is refreshed so the screen can show all three
      unpriced    master has no price → NOT copied, reported (decision 5)
      retired     on the sheet, no longer on the master list → kept, reported

    `apply=False` is the dry run behind the diff preview and the drift badge.
    Does not commit; does not recalc — the router does both.
    """
    result = PullResult(estimate_id=estimate_id, applied=apply)
    existing = {
        _key(r.kind, r.scope, r.ref_id, r.ref_key): r
        for r in db.scalars(
            select(EstimatePrice).where(EstimatePrice.estimate_id == estimate_id)
        ).all()
    }
    seen: set[tuple] = set()
    now = datetime.now(timezone.utc)

    for item in _master_list(db):
        key = _key(item["kind"], item["scope"], item["ref_id"], item["ref_key"])
        seen.add(key)
        master = item["catalog_value"]
        row = existing.get(key)
        summary = {"kind": item["kind"], "scope": item["scope"], "ref_id": item["ref_id"],
                   "ref_key": item["ref_key"], "label": item["label"], "unit": item["unit"]}

        if master is None:
            result.unpriced.append({**summary, "on_sheet": row is not None,
                                    "value": str(row.value) if row else None})
            continue
        master = _d(master).quantize(_Q4)

        if row is None:
            result.new.append({**summary, "catalog_value": str(master)})
            if apply:
                db.add(EstimatePrice(
                    estimate_id=estimate_id, kind=item["kind"], scope=item["scope"],
                    ref_id=item["ref_id"], ref_key=item["ref_key"],
                    label=item["label"], unit=item["unit"], category=item["category"],
                    catalog_value=master, value=master, is_edited=False, pulled_at=now,
                ))
            continue

        was = _d(row.catalog_value).quantize(_Q4) if row.catalog_value is not None else None
        if was == master:
            result.unchanged += 1
            continue

        entry = {**summary, "was": str(was) if was is not None else None,
                 "now": str(master), "yours": str(_d(row.value).quantize(_Q4))}
        if row.is_edited:
            result.conflicts.append(entry)
            if apply:
                row.catalog_value = master     # so the screen shows was/now/yours
                row.pulled_at = now
        else:
            result.changed.append(entry)
            if apply:
                row.catalog_value = master
                row.value = master
                row.label = item["label"]
                row.pulled_at = now

    for key, row in existing.items():
        if key not in seen:
            result.retired.append({"kind": row.kind, "scope": row.scope, "ref_id": row.ref_id,
                                   "ref_key": row.ref_key, "label": row.label,
                                   "value": str(row.value)})

    if apply:
        db.flush()
    return result


def drift(db: Session, estimate_id: UUID) -> PullResult:
    """What has moved on the master list since this sheet was pulled. Read-only."""
    return pull_prices(db, estimate_id, apply=False)


# ------------------------------------------------------------------ edit ----


def set_price(
    db: Session,
    price: EstimatePrice,
    *,
    value: Decimal | None = None,
    note: str | None = None,
    reset: bool = False,
) -> EstimatePrice:
    """
    Change what this job pays for one item.

    `reset=True` puts the master price back and clears `is_edited` — the one
    way a row stops being protected from a pull. Setting `value` to the master
    number by hand does NOT clear it: that is still a decision, and a later
    pull must not quietly turn it back into a follower.
    """
    if reset:
        if price.catalog_value is None:
            raise ValueError("no master price to reset to")
        price.value = price.catalog_value
        price.is_edited = False
        price.note = None
    else:
        if value is not None:
            # A mix, material or machine at $0 is the bug decision 5 exists to
            # stop. A RATE at zero is a statement — paving pumps nothing,
            # sidewalk has no curb labor — and the tables carry several.
            if _d(value) < 0 or (_d(value) == 0 and price.kind not in ("setting", "assembly_rate")):
                raise ValueError("a price must be greater than zero — clear the item instead")
            price.value = _d(value).quantize(_Q4)
            price.is_edited = True
        if note is not None:
            price.note = note or None
    price.updated_at = datetime.now(timezone.utc)
    db.flush()
    return price


def sheet_rows(db: Session, estimate_id: UUID) -> list[EstimatePrice]:
    return list(
        db.scalars(
            select(EstimatePrice)
            .where(EstimatePrice.estimate_id == estimate_id)
            .order_by(EstimatePrice.kind, EstimatePrice.category, EstimatePrice.label)
        ).all()
    )
