"""
The proposal (sql/080): one per estimate, seeded from the takeoff, edited on
its own page, and downloaded as the bid form.

Paths:
    /proposals                       one per estimate — find, make, read, edit, delete
    /proposals/{id}/refresh          pull the estimate onto it again
    /proposals/{id}/sections/bulk    the sections grid
    /proposals/{id}/items/{block}    one bullet block or the terms, whole
    /proposals/{id}/xlsx             the form
    /proposal-sections/{id}/lines/bulk, /proposal-sections/{id}, /proposal-lines/{id}
    /proposal-library                the company's standing text (a senior estimator edits it)
"""

from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimate import Estimate
from app.models.proposal import BLOCKS, Proposal, ProposalItem, ProposalLibraryItem, ProposalLine, ProposalSection
from app.schemas.proposal import (
    ItemsUpdate,
    LibraryRead,
    ProposalCreate,
    ProposalLinesBulk,
    ProposalRead,
    ProposalSectionsBulk,
    ProposalUpdate,
    RefreshResult,
)
from app.services.proposal_xlsx import build_workbook
from app.services.proposals import library_read, proposal_read, refresh_from_estimate, seed_proposal

router = APIRouter(tags=["proposals"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _proposal_or_404(db: Session, proposal_id: UUID) -> Proposal:
    row = db.get(Proposal, proposal_id)
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return row


def _section_or_404(db: Session, section_id: UUID) -> ProposalSection:
    row = db.get(ProposalSection, section_id)
    if not row:
        raise HTTPException(status_code=404, detail="Proposal section not found")
    return row


def _block_or_404(block: str) -> str:
    if block not in BLOCKS:
        raise HTTPException(status_code=404, detail=f"No block named {block!r}; one of {', '.join(BLOCKS)}")
    return block


def _read(db: Session, proposal: Proposal) -> ProposalRead:
    return ProposalRead(**proposal_read(db, proposal))


def _touch(row) -> None:
    row.updated_at = datetime.now(timezone.utc)


# ------------------------------------------------------------ proposals ----


@router.get("/proposals", response_model=ProposalRead)
def proposal_for_estimate(estimate_id: UUID = Query(...), db: Session = Depends(get_db)) -> ProposalRead:
    row = db.scalars(select(Proposal).where(Proposal.estimate_id == estimate_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="This estimate has no proposal yet")
    return _read(db, row)


@router.post("/proposals", response_model=ProposalRead, status_code=status.HTTP_201_CREATED)
def create_proposal(body: ProposalCreate, db: Session = Depends(get_db)) -> ProposalRead:
    estimate = db.get(Estimate, body.estimate_id)
    if not estimate:
        raise HTTPException(status_code=400, detail="estimate_id not found")
    if db.scalars(select(Proposal).where(Proposal.estimate_id == body.estimate_id)).first() is not None:
        raise HTTPException(status_code=409, detail="This estimate already has a proposal")
    row = seed_proposal(db, estimate)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.get("/proposals/{proposal_id}", response_model=ProposalRead)
def get_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> ProposalRead:
    return _read(db, _proposal_or_404(db, proposal_id))


@router.patch("/proposals/{proposal_id}", response_model=ProposalRead)
def update_proposal(proposal_id: UUID, body: ProposalUpdate, db: Session = Depends(get_db)) -> ProposalRead:
    row = _proposal_or_404(db, proposal_id)
    data = body.model_dump(exclude_unset=True)
    if "drawings" in data and data["drawings"] is not None:
        # JSONB holds strings, not dates.
        data["drawings"] = [d.model_dump(mode="json") for d in body.drawings]
    for key, value in data.items():
        if value is None and key in ("rev", "proposal_date", "intro", "payment_terms", "drawings"):
            continue  # cannot be empty; a blank means "leave it"
        setattr(row, key, value)
    _touch(row)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.delete("/proposals/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> None:
    row = _proposal_or_404(db, proposal_id)
    db.delete(row)
    db.commit()


@router.post("/proposals/{proposal_id}/refresh", response_model=RefreshResult)
def refresh_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> RefreshResult:
    row = _proposal_or_404(db, proposal_id)
    counts = refresh_from_estimate(db, row)
    _touch(row)
    db.commit()
    db.refresh(row)
    return RefreshResult(**counts, proposal=_read(db, row))


@router.put("/proposals/{proposal_id}/sections/bulk", response_model=ProposalRead)
def bulk_save_sections(
    proposal_id: UUID, body: ProposalSectionsBulk, db: Session = Depends(get_db)
) -> ProposalRead:
    """The sections grid in one request: titles and order; new rows appended."""
    proposal = _proposal_or_404(db, proposal_id)
    existing = {
        r.id: r
        for r in db.scalars(select(ProposalSection).where(ProposalSection.proposal_id == proposal_id)).all()
    }
    seen: set[UUID] = set()
    last = max((r.sort_order for r in existing.values()), default=0)
    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id"})
        if data.get("title") is None:
            data.pop("title", None)
        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(status_code=400, detail=f"section {incoming.id} is not on this proposal")
            for key, value in data.items():
                if value is not None:
                    setattr(row, key, value)
            _touch(row)
        else:
            if "sort_order" not in data or data["sort_order"] is None:
                last += 10
                data["sort_order"] = last + order
            row = ProposalSection(proposal_id=proposal_id, title=data.pop("title", ""), **data)
            db.add(row)
        db.flush()
        seen.add(row.id)
    if body.delete_missing:
        for rid, row in existing.items():
            if rid not in seen:
                db.delete(row)
        db.flush()
    _touch(proposal)
    db.commit()
    db.refresh(proposal)
    return _read(db, proposal)


@router.put("/proposals/{proposal_id}/items/{block}", response_model=ProposalRead)
def replace_items(
    proposal_id: UUID, block: str, body: ItemsUpdate, db: Session = Depends(get_db)
) -> ProposalRead:
    """One block, whole: the strings sent are the block, in that order."""
    proposal = _proposal_or_404(db, proposal_id)
    _block_or_404(block)
    for row in db.scalars(
        select(ProposalItem).where(ProposalItem.proposal_id == proposal_id, ProposalItem.block == block)
    ).all():
        db.delete(row)
    db.flush()
    for i, text in enumerate(body.items):
        if text.strip():
            db.add(ProposalItem(proposal_id=proposal_id, block=block, sort_order=(i + 1) * 10, text=text.strip()))
    _touch(proposal)
    db.commit()
    db.refresh(proposal)
    return _read(db, proposal)


@router.get("/proposals/{proposal_id}/xlsx")
def download_xlsx(proposal_id: UUID, db: Session = Depends(get_db)) -> Response:
    """The form. The file is named to the playbook's standard, revision and date included."""
    proposal = _proposal_or_404(db, proposal_id)
    read = proposal_read(db, proposal)
    content = build_workbook(read)
    name = read["file_name"]
    ascii_name = name.encode("ascii", "ignore").decode() or "Proposal.xlsx"
    return Response(
        content=content,
        media_type=XLSX,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
            "X-Proposal-File-Name": quote(name),
        },
    )


# --------------------------------------------------- sections and lines ----


@router.put("/proposal-sections/{section_id}/lines/bulk", response_model=ProposalRead)
def bulk_save_lines(
    section_id: UUID, body: ProposalLinesBulk, db: Session = Depends(get_db)
) -> ProposalRead:
    """One section's lines grid in one request. Returns the whole proposal, totals and all."""
    section = _section_or_404(db, section_id)
    proposal = _proposal_or_404(db, section.proposal_id)
    existing = {
        r.id: r
        for r in db.scalars(select(ProposalLine).where(ProposalLine.proposal_section_id == section_id)).all()
    }
    seen: set[UUID] = set()
    last = max((r.sort_order for r in existing.values()), default=0)
    for order, incoming in enumerate(body.rows):
        data = incoming.model_dump(exclude_unset=True, exclude={"id"})
        if incoming.id is not None:
            row = existing.get(incoming.id)
            if row is None:
                raise HTTPException(status_code=400, detail=f"line {incoming.id} is not in this section")
            for key, value in data.items():
                if key in ("description", "status") and value is None:
                    continue
                setattr(row, key, value)
            _touch(row)
        else:
            if data.get("sort_order") is None:
                last += 10
                data["sort_order"] = last + order
            if data.get("description") is None:
                data["description"] = ""
            if data.get("status") is None:
                data["status"] = "INCLUDED"
            row = ProposalLine(proposal_section_id=section_id, **data)
            db.add(row)
        db.flush()
        seen.add(row.id)
    if body.delete_missing:
        for rid, row in existing.items():
            if rid not in seen:
                db.delete(row)
        db.flush()
    _touch(section)
    db.commit()
    db.refresh(proposal)
    return _read(db, proposal)


@router.delete("/proposal-sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(section_id: UUID, db: Session = Depends(get_db)) -> None:
    row = _section_or_404(db, section_id)
    db.delete(row)
    db.commit()


@router.delete("/proposal-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line(line_id: UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(ProposalLine, line_id)
    if not row:
        raise HTTPException(status_code=404, detail="Proposal line not found")
    db.delete(row)
    db.commit()


# -------------------------------------------------------------- library ----


@router.get("/proposal-library", response_model=LibraryRead)
def get_library(db: Session = Depends(get_db)) -> LibraryRead:
    return LibraryRead(blocks=library_read(db))


@router.put("/proposal-library/{block}", response_model=LibraryRead)
def replace_library_block(block: str, body: ItemsUpdate, db: Session = Depends(get_db)) -> LibraryRead:
    """One block of the standing text, whole. Proposals already made keep their own copies."""
    _block_or_404(block)
    for row in db.scalars(select(ProposalLibraryItem).where(ProposalLibraryItem.block == block)).all():
        db.delete(row)
    db.flush()
    for i, text in enumerate(body.items):
        if text.strip():
            db.add(ProposalLibraryItem(block=block, sort_order=(i + 1) * 10, text=text.strip()))
    db.commit()
    return LibraryRead(blocks=library_read(db))
