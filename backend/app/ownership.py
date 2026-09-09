"""
Which project a takeoff row belongs to, and who is on it (2026-09-09).

Chad: "estimators and lower.. no delete of anything" — records, that is: a
bid, a daily report, the form's lists, a section, a proposal, a catalog row
are a senior estimator's to delete — "and only estimates they are assigned
to can they delete rows out of estimate sections". A row inside a takeoff (a
pour, a wall run, a beam run, a beam type, a deck level, a pier group, a
column or panel type, a misc item, a grade beam, a proposal section or
line) an estimator may delete on an estimate whose project lists them.

app/policy.py asks `project_of` which project a row's delete path leads to
and `assigned` whether the person is on it. A path that is not a row, or a
row that is gone, answers None and the route's own 404 follows.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.beam_run import BeamRun
from app.models.beam_type import EstimateBeamType
from app.models.column_type import ColumnType
from app.models.deck_level import DeckLevel
from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.models.grade_beam import GradeBeam
from app.models.misc_item import MiscItem
from app.models.mono_slab import MonoSlab
from app.models.panel_type import PanelType
from app.models.pier_group import PierGroup
from app.models.project import ProjectEstimator
from app.models.proposal import Proposal, ProposalLine, ProposalSection
from app.models.wall_run import WallRun

# Rows that hang off a section, by the path that deletes them.
SECTION_ROWS = {
    "mono-slabs": MonoSlab,
    "wall-runs": WallRun,
    "beam-runs": BeamRun,
    "pier-groups": PierGroup,
    "deck-levels": DeckLevel,
    "column-types": ColumnType,
    "panel-types": PanelType,
    "misc-items": MiscItem,
    "beam-types": EstimateBeamType,
}
ROW_KINDS = tuple(SECTION_ROWS) + ("grade-beams", "proposal-sections", "proposal-lines")
ROW_DELETE = re.compile(r"/api/(" + "|".join(re.escape(k) for k in ROW_KINDS) + r")/([^/]+)")


def _uuid(raw: str) -> UUID | None:
    try:
        return UUID(raw)
    except ValueError:
        return None


def project_of(db: Session, path: str) -> UUID | None:
    """The project a row's delete path leads to; None when it is not a row or the row is gone."""
    m = ROW_DELETE.fullmatch(path)
    if not m:
        return None
    kind, row_id = m.group(1), _uuid(m.group(2))
    if row_id is None:
        return None
    if kind in ("proposal-sections", "proposal-lines"):
        if kind == "proposal-lines":
            line = db.get(ProposalLine, row_id)
            psec = db.get(ProposalSection, line.proposal_section_id) if line else None
        else:
            psec = db.get(ProposalSection, row_id)
        proposal = db.get(Proposal, psec.proposal_id) if psec else None
        estimate = db.get(Estimate, proposal.estimate_id) if proposal else None
        return estimate.project_id if estimate else None
    if kind == "grade-beams":
        beam = db.get(GradeBeam, row_id)
        slab = db.get(MonoSlab, beam.mono_slab_id) if beam else None
        section_id = slab.section_id if slab else None
    else:
        row = db.get(SECTION_ROWS[kind], row_id)
        section_id = row.section_id if row else None
    if section_id is None:
        return None
    section = db.get(EstimateSection, section_id)
    estimate = db.get(Estimate, section.estimate_id) if section else None
    return estimate.project_id if estimate else None


def assigned(db: Session, project_id: UUID, estimator_id: UUID) -> bool:
    return (
        db.scalar(
            select(ProjectEstimator.estimator_id).where(
                ProjectEstimator.project_id == project_id, ProjectEstimator.estimator_id == estimator_id
            )
        )
        is not None
    )
