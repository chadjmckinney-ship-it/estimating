"""
Re-derive an estimate's stored results from current inputs.

Every quantity in this system is stored, not computed on read: mono_slabs.calc_*
columns, and the estimate_forming / labor / equipment line tables. That makes
reads cheap but means any change to an upstream input — pour fields, estimate
waste factors, or company defaults in system_settings — leaves stale numbers
behind until something rewrites them. This module is that something.

Takeoffs are only refreshed if they were already stored. Opening an estimate is
what creates them, and a recalc should not conjure a labor package for an
estimate nobody has costed yet.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.models.estimate_equipment import EstimateEquipmentSummary
from app.models.estimate_forming import EstimateFormingSummary
from app.models.estimate_labor import EstimateLaborSummary
from app.services.calc import refresh_section_slab_calcs
from app.models.estimate_section import COLUMN_KINDS, DECK_KINDS
from app.services.costing import PIER_KINDS, WALL_KINDS
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor

# Which system_settings keys feed which derivation. Anything unmatched is
# treated as harmless (no recalc) — see settings_scope().
_POUR_KEYS = frozenset(
    {
        "waste_concrete",
        "waste_sand",
        "waste_poly",
        "waste_rebar",
        "support_rebar_lb_per_sf",
        "pt_lb_per_sf",
    }
)
_FORMING_KEYS = frozenset({"form_percent", "form_waste"})
# Keys that feed the EQUIPMENT lines without being named `equip_`. Mobilization
# is one (sql/053): it seeds a contract-services line on every assembly, so a
# change to it has to rewrite them, and the prefix rule below would have said
# "this key feeds no stored calculation" — which is how a company rate change
# reaches nothing and nobody notices.
_EQUIPMENT_KEYS = frozenset({"mobilization_ls"})
# Priced at cost time from stored quantities, so a change only needs the costing
# pass — but that runs inside the pour refresh, so ask for pours.
_COSTING_KEYS = frozenset(
    {
        "sales_tax_pct",
        "equip_fuel_maint_pct",
        # The vapor barrier and its tape are priced at cost time too. An estimate
        # that names neither takes the company default, so changing a default
        # moves real money on every estimate that hasn't chosen for itself.
        "default_vapor_barrier_material_id",
        "default_vapor_tape_material_id",
        "vapor_tape_rolls_per_barrier_roll",
    }
)

# A bulk recalc — a catalog price change or a company-default change — must not
# reprice work that is already out the door. A job bid last spring keeps the
# numbers it was bid with. Direct edits to an estimate still recalculate it
# (recalc_estimate below), and so does its own Recalculate button; this only
# governs the sweep across every estimate.
FROZEN_STATUSES = frozenset({"final", "archived"})


def is_frozen(estimate: Estimate) -> bool:
    return (estimate.status or "draft") in FROZEN_STATUSES


def settings_scope(keys: list[str]) -> dict[str, bool]:
    """Map changed setting keys to the derivations they invalidate."""
    scope = {"pours": False, "forming": False, "labor": False, "equipment": False}
    for key in keys:
        if key in _POUR_KEYS:
            # Pour quantities drive forming (rebar/SF), labor (SF/rebar) and
            # equipment (pumping CY), so a pour change ripples into all three.
            scope.update(pours=True, forming=True, labor=True, equipment=True)
        elif key in _COSTING_KEYS:
            scope["pours"] = True
        elif key in _FORMING_KEYS:
            scope["forming"] = True
        elif key.startswith("labor_"):
            scope["labor"] = True
            # Equipment days ride on the superintendent duration.
            scope["equipment"] = True
        elif key.startswith("equip_") or key in _EQUIPMENT_KEYS:
            scope["equipment"] = True
    return scope


def recalc_section(
    db: Session,
    section: EstimateSection,
    *,
    pours: bool = True,
    forming: bool = True,
    labor: bool = True,
    equipment: bool = True,
) -> dict[str, Any]:
    """
    Rewrite stored results for one section. Does not commit.

    Order matters: pours feed the takeoff drivers, and equipment reads the
    superintendent days that the labor summary produces.
    """
    done: dict[str, Any] = {
        "section_id": str(section.id),
        "name": section.name,
        "kind": section.kind,
        "pours": 0,
        "forming": False,
        "labor": False,
        "equipment": False,
    }

    if pours:
        # Piers are not pours. Same idea — stored quantities, rewritten from
        # current inputs — different rows (sql/037).
        if section.kind in PIER_KINDS:
            from app.services.piers import refresh_section_pier_calcs

            done["pours"] = refresh_section_pier_calcs(db, section)
        elif section.kind in WALL_KINDS:
            # Nor are wall runs. Third takeoff shape, same contract (sql/040).
            from app.services.walls import refresh_section_wall_calcs

            done["pours"] = refresh_section_wall_calcs(db, section)
        elif section.kind in COLUMN_KINDS:
            # Fourth shape: a column TYPE and a count (sql/045).
            from app.services.columns import refresh_section_column_calcs

            done["pours"] = refresh_section_column_calcs(db, section)
        elif section.kind in DECK_KINDS:
            # Fifth shape: a deck LEVEL (sql/052).
            from app.services.cip_deck import refresh_section_deck_calcs

            done["pours"] = refresh_section_deck_calcs(db, section)
        else:
            done["pours"] = refresh_section_slab_calcs(db, section)

    # UNCONDITIONAL, and outside the `if pours:` above — this is load-bearing.
    #
    # The three refreshes below read their drivers in raw SQL, and sessions run
    # with autoflush=False (app/db.py). So anything written through the ORM and
    # not yet flushed is invisible to them: they see pre-edit rows.
    #
    # This flush used to sit inside `if pours:`, which made it look sufficient
    # — the pour recalc is the obvious writer. But `pours=False` exists exactly
    # for callers that have ALREADY written the geometry themselves and only
    # want the takeoffs rebuilt, and those callers are the ones whose writes
    # were pending. `routers/grade_beams.py` is the only such caller, and it
    # was returning 500 for unrelated reasons, so nothing ever exercised the
    # path: adding 500 LF of reinforced grade beam moved the pour from 2,447 lb
    # to 5,931 lb and left `estimate_labor_summary` on 21,944.977.
    #
    # Equipment happened to survive it, which is the detail worth remembering:
    # `_super_days` carries its own flush (added 2026-09-01 after the zero-day
    # rental ladder), so by the time equipment ran the rows were on disk. Labor
    # runs first and has no such flush. One flush in one reader rescued one of
    # three consumers and disguised the hole in the other two.
    db.flush()

    if forming and db.get(EstimateFormingSummary, section.id) is not None:
        refresh_and_store_forming(db, section.id)
        done["forming"] = True

    if labor and db.get(EstimateLaborSummary, section.id) is not None:
        refresh_and_store_labor(db, section.id)
        done["labor"] = True

    if equipment and db.get(EstimateEquipmentSummary, section.id) is not None:
        refresh_and_store_equipment(db, section.id)
        done["equipment"] = True

    from app.services.costing import refresh_pour_costs

    costed = refresh_pour_costs(db, section)
    done["cost"] = costed.get("total_cost")
    done["sale"] = costed.get("total_sale")
    return done


def recalc_estimate(
    db: Session,
    estimate: Estimate,
    **flags: bool,
) -> dict[str, Any]:
    """
    Rewrite every section of a job, then roll the job up. Commits.

    The estimate computes nothing of its own — it adds up what its sections
    priced, each at its own markup and tax treatment.
    """
    from sqlalchemy import select

    from app.services.costing import refresh_estimate_totals

    sections = list(
        db.scalars(
            select(EstimateSection)
            .where(EstimateSection.estimate_id == estimate.id)
            .order_by(EstimateSection.sort_order, EstimateSection.created_at)
        ).all()
    )
    done: dict[str, Any] = {
        "estimate_id": str(estimate.id),
        "name": estimate.name,
        "sections": [recalc_section(db, s, **flags) for s in sections],
    }
    db.flush()
    totals = refresh_estimate_totals(db, estimate)
    done["cost"] = totals["total_cost"]
    done["sale"] = totals["total_sale"]
    db.commit()
    return done


def recalc_estimate_id(db: Session, estimate_id: UUID, **flags: bool) -> dict[str, Any] | None:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        return None
    return recalc_estimate(db, estimate, **flags)


def recalc_all_estimates(
    db: Session, *, include_frozen: bool = False, **flags: bool
) -> dict[str, Any]:
    """
    Rewrite the open estimates. Use after changing company defaults or catalog
    prices — including edits made straight through psql, which no endpoint can
    intercept.

    Frozen estimates (final, archived) are skipped and reported by name, so a
    price change never moves a bid that has already gone out. Pass
    include_frozen=True to override, deliberately.
    """
    stmt = select(Estimate).order_by(Estimate.name)
    estimates = list(db.scalars(stmt).all())

    done: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for e in estimates:
        if not include_frozen and is_frozen(e):
            skipped.append({"estimate_id": str(e.id), "name": e.name, "status": e.status})
            continue
        done.append(recalc_estimate(db, e, **flags))

    return {"recalculated": done, "skipped": skipped}
