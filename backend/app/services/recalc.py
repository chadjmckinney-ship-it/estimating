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
from app.models.estimate_equipment import EstimateEquipmentSummary
from app.models.estimate_forming import EstimateFormingSummary
from app.models.estimate_labor import EstimateLaborSummary
from app.services.calc import refresh_estimate_slab_calcs
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


def settings_scope(keys: list[str]) -> dict[str, bool]:
    """Map changed setting keys to the derivations they invalidate."""
    scope = {"pours": False, "forming": False, "labor": False, "equipment": False}
    for key in keys:
        if key in _POUR_KEYS:
            # Pour quantities drive forming (rebar/SF), labor (SF/rebar) and
            # equipment (pumping CY), so a pour change ripples into all three.
            scope.update(pours=True, forming=True, labor=True, equipment=True)
        elif key in _FORMING_KEYS:
            scope["forming"] = True
        elif key.startswith("labor_"):
            scope["labor"] = True
            # Equipment days ride on the superintendent duration.
            scope["equipment"] = True
        elif key.startswith("equip_"):
            scope["equipment"] = True
    return scope


def recalc_estimate(
    db: Session,
    estimate: Estimate,
    *,
    pours: bool = True,
    forming: bool = True,
    labor: bool = True,
    equipment: bool = True,
) -> dict[str, Any]:
    """
    Rewrite stored results for one estimate. Commits.

    Order matters: pours feed the takeoff drivers, and equipment reads the
    superintendent days that the labor summary produces.
    """
    done: dict[str, Any] = {
        "estimate_id": str(estimate.id),
        "name": estimate.name,
        "pours": 0,
        "forming": False,
        "labor": False,
        "equipment": False,
    }

    if pours:
        done["pours"] = refresh_estimate_slab_calcs(db, estimate)
        db.flush()

    if forming and db.get(EstimateFormingSummary, estimate.id) is not None:
        refresh_and_store_forming(db, estimate.id)
        done["forming"] = True

    if labor and db.get(EstimateLaborSummary, estimate.id) is not None:
        refresh_and_store_labor(db, estimate.id)
        done["labor"] = True

    if equipment and db.get(EstimateEquipmentSummary, estimate.id) is not None:
        refresh_and_store_equipment(db, estimate.id)
        done["equipment"] = True

    db.commit()
    return done


def recalc_estimate_id(db: Session, estimate_id: UUID, **flags: bool) -> dict[str, Any] | None:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        return None
    return recalc_estimate(db, estimate, **flags)


def recalc_all_estimates(db: Session, **flags: bool) -> list[dict[str, Any]]:
    """
    Rewrite every estimate. Use after changing company defaults — including
    edits made straight through psql, which no endpoint can intercept.
    """
    estimates = list(db.scalars(select(Estimate).order_by(Estimate.name)).all())
    return [recalc_estimate(db, e, **flags) for e in estimates]
