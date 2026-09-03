"""
Saving a whole grid of pours at once.

Paving is entered as a table — up to twenty-five areas across sixteen columns —
and the section's forming, labor and equipment all key off the section totals,
so a save per field would re-run all three on every keystroke. This writes the
rows first and recalculates the section once.

It lives here rather than in the router so it can be tested against a session
whose writes roll back; the router is a thin wrapper over it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.estimate_section import EstimateSection
from app.models.mix_design import MixDesign
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs


class BulkSaveError(ValueError):
    """A row the caller has to fix; carries the message shown to them."""


def bulk_save_pours(
    db: Session,
    section: EstimateSection,
    rows: list[dict[str, Any]],
    *,
    delete_missing: bool = False,
) -> dict[str, Any]:
    """
    Create, update and (optionally) delete pours to match `rows`. Commits.

    Each row is a dict of pour fields; an `id` means update that pour, no `id`
    means create one. Rows the grid did not send are left alone unless
    delete_missing is set — a save that quietly deletes work the user could not
    see is a worse failure than a row that has to be deleted twice.
    """
    existing = {
        r.id: r
        for r in db.scalars(
            select(MonoSlab).where(MonoSlab.section_id == section.id)
        ).all()
    }
    created = updated = deleted = 0
    seen: set[UUID] = set()

    for order, incoming in enumerate(rows):
        data = {k: v for k, v in incoming.items() if k != "id"}
        row_id = incoming.get("id")

        mix_id = data.get("mix_design_id")
        if mix_id is not None and not db.get(MixDesign, mix_id):
            raise BulkSaveError(f"mix_design_id {mix_id} not found")
        data.setdefault("sort_order", order * 10)

        if row_id is not None:
            row = existing.get(row_id if isinstance(row_id, UUID) else UUID(str(row_id)))
            if row is None:
                raise BulkSaveError(f"pour {row_id} is not in this section")
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            if data.get("square_footage") is None or data.get("thickness_in") is None:
                raise BulkSaveError(
                    "a new row needs at least square_footage and thickness_in"
                )
            row = MonoSlab(section_id=section.id, **data)
            db.add(row)
            created += 1
        db.flush()
        seen.add(row.id)

    if delete_missing:
        for slab_id, row in existing.items():
            if slab_id not in seen:
                db.delete(row)
                deleted += 1
        db.flush()

    for row in db.scalars(
        select(MonoSlab).where(MonoSlab.section_id == section.id)
    ).all():
        refresh_mono_slab_calcs(db, row, section)
    db.flush()

    # Quantities moved, so everything derived from them has to move too. This
    # is the staleness the stored calc_* columns invite, and the one thing a
    # bulk save must not skip.
    from app.services.recalc import recalc_section

    recalc_section(db, section)
    db.commit()

    return {"created": created, "updated": updated, "deleted": deleted}
