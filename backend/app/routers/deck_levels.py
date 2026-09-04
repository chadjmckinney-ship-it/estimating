"""
Deck levels — one level of a cast-in-place elevated deck (sql/052).

Mirrors routers/column_types.py, including the rule learned on piers, repeated
on walls and paid for on columns: **every write path re-runs the WHOLE
section**, not the row it touched.

Two reasons here, and both bite. A lump rebar or PT quote is spread across the
levels by weight, so changing one level's area or steel moves what every other
level carries. And the lumber block rides `perm edge LF + GB form FF` summed
across the section — edit one level's edge and the 2x4, 2x6, 2x10, plywood
and stake lines all move for the whole deck.

The columns router learned this the expensive way: PATCHing one type's
quantity left the superintendent on 17 days where the new count demanded
107.5, and the section $436,826.42 light with a stale rental ladder behind it.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.beam_type import EstimateBeamType
from app.models.deck_level import DeckLevel, DeckLevelBeam
from app.models.estimate_section import DECK_KINDS, EstimateSection
from app.models.mix_design import MixDesign
from app.schemas.deck_level import (
    DeckLevelBulkResult,
    DeckLevelBulkSave,
    DeckLevelCreate,
    DeckLevelRead,
    DeckLevelUpdate,
    DeckTotals,
)
from app.services.cip_deck import section_deck_totals

router = APIRouter(prefix="/deck-levels", tags=["deck-levels"])


def _section_or_404(db: Session, section_id: UUID) -> EstimateSection:
    section = db.get(EstimateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.kind not in DECK_KINDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Section {section.name!r} is a {section.kind} section, "
                "not a CIP deck"
            ),
        )
    return section


def _recost(db: Session, section: EstimateSection | None) -> None:
    from app.services.recalc import recalc_section

    if section is not None:
        recalc_section(db, section)


def _set_beams(db: Session, level: DeckLevel, beams, section_id: UUID) -> None:
    """
    Replace a level's beams with what was sent.

    A beam type belongs to a SECTION, so one that is not on this section is a
    400 rather than a silent skip: an unresolved beam is a level with no beam
    steel and no beam concrete, and nothing on screen to notice.
    """
    db.execute(
        DeckLevelBeam.__table__.delete().where(
            DeckLevelBeam.deck_level_id == level.id
        )
    )
    for order, b in enumerate(beams or []):
        bt = db.get(EstimateBeamType, b.beam_type_id)
        if bt is None or bt.section_id != section_id:
            raise HTTPException(
                status_code=400,
                detail=f"beam type {b.beam_type_id} is not on this section",
            )
        db.add(
            DeckLevelBeam(
                deck_level_id=level.id,
                beam_type_id=b.beam_type_id,
                length_lf=b.length_lf,
                notes=b.notes,
                sort_order=b.sort_order or order * 10,
            )
        )
    db.flush()


def _rows(db: Session, section_id: UUID) -> list[DeckLevelRead]:
    return [
        DeckLevelRead.model_validate(r)
        for r in db.scalars(
            select(DeckLevel)
            .where(DeckLevel.section_id == section_id)
            .order_by(DeckLevel.sort_order, DeckLevel.created_at)
        ).all()
    ]


@router.get("", response_model=list[DeckLevelRead])
def list_deck_levels(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> list[DeckLevelRead]:
    return _rows(db, section_id)


@router.get("/totals", response_model=DeckTotals)
def deck_totals(
    section_id: UUID = Query(...), db: Session = Depends(get_db)
) -> DeckTotals:
    return DeckTotals(section_id=section_id, **section_deck_totals(db, section_id))


@router.post("", response_model=DeckLevelRead, status_code=status.HTTP_201_CREATED)
def create_deck_level(
    body: DeckLevelCreate, db: Session = Depends(get_db)
) -> DeckLevelRead:
    section = _section_or_404(db, body.section_id)
    if body.mix_design_id and not db.get(MixDesign, body.mix_design_id):
        raise HTTPException(status_code=400, detail="mix_design_id not found")

    data = body.model_dump(exclude={"beams"})
    row = DeckLevel(**data)
    db.add(row)
    db.flush()
    _set_beams(db, row, body.beams, body.section_id)
    _recost(db, section)
    db.commit()
    db.refresh(row)
    return DeckLevelRead.model_validate(row)


@router.put("/bulk", response_model=DeckLevelBulkResult)
def bulk_save_deck_levels(
    body: DeckLevelBulkSave, db: Session = Depends(get_db)
) -> DeckLevelBulkResult:
    """Save the whole grid in one request, then recalculate the section once."""
    section = _section_or_404(db, body.section_id)

    existing = {
        r.id: r
        for r in db.scalars(
            select(DeckLevel).where(DeckLevel.section_id == body.section_id)
        ).all()
    }
    created = updated = deleted = 0
    seen: set[UUID] = set()

    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id", "beams"})
        mix_id = data.get("mix_design_id")
        if mix_id is not None and not db.get(MixDesign, mix_id):
            raise HTTPException(
                status_code=400, detail=f"mix_design_id {mix_id} not found"
            )
        data.setdefault("sort_order", order * 10)

        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"deck level {incoming.id} is not in this section",
                )
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            # A level with no area is not a level. Everything on this
            # assembly — the labor, the allocation, the pour — is square feet.
            if not data.get("area_sf"):
                raise HTTPException(
                    status_code=400, detail="a new level needs an area"
                )
            row = DeckLevel(section_id=body.section_id, **data)
            db.add(row)
            created += 1
        db.flush()
        # Beams sent → replace. Beams omitted → left alone, so a grid that
        # only edits areas cannot silently strip the beam schedule.
        if incoming.beams is not None:
            _set_beams(db, row, incoming.beams, body.section_id)
        seen.add(row.id)

    # Rows the grid did not send are LEFT ALONE unless delete_missing is set.
    # The grid scrolls and a request can be truncated; neither should cost a
    # level.
    if body.delete_missing:
        for rid, row in existing.items():
            if rid not in seen:
                db.delete(row)
                deleted += 1
        db.flush()

    _recost(db, section)
    db.commit()

    return DeckLevelBulkResult(
        section_id=body.section_id,
        created=created,
        updated=updated,
        deleted=deleted,
        rows=_rows(db, body.section_id),
        totals=DeckTotals(
            section_id=body.section_id, **section_deck_totals(db, body.section_id)
        ),
    )


@router.get("/{level_id}", response_model=DeckLevelRead)
def get_deck_level(level_id: UUID, db: Session = Depends(get_db)) -> DeckLevelRead:
    row = db.get(DeckLevel, level_id)
    if not row:
        raise HTTPException(status_code=404, detail="Deck level not found")
    return DeckLevelRead.model_validate(row)


@router.patch("/{level_id}", response_model=DeckLevelRead)
def update_deck_level(
    level_id: UUID, body: DeckLevelUpdate, db: Session = Depends(get_db)
) -> DeckLevelRead:
    row = db.get(DeckLevel, level_id)
    if not row:
        raise HTTPException(status_code=404, detail="Deck level not found")
    data = body.model_dump(exclude_unset=True, exclude={"beams"})
    if data.get("mix_design_id") is not None and not db.get(
        MixDesign, data["mix_design_id"]
    ):
        raise HTTPException(status_code=400, detail="mix_design_id not found")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    if body.beams is not None:
        _set_beams(db, row, body.beams, row.section_id)

    _recost(db, db.get(EstimateSection, row.section_id))
    db.commit()
    db.refresh(row)
    return DeckLevelRead.model_validate(row)


@router.delete("/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck_level(level_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(DeckLevel, level_id)
    if not row:
        raise HTTPException(status_code=404, detail="Deck level not found")
    section = db.get(EstimateSection, row.section_id)
    db.delete(row)
    db.flush()
    _recost(db, section)
    db.commit()
