from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Kinds live on the beam type now (sql/025); re-exported so existing imports work.
from app.schemas.beam_type import BEAM_KINDS, BeamKind

__all__ = [
    "BEAM_KINDS",
    "BeamKind",
    "GradeBeamRead",
    "GradeBeamCreate",
    "GradeBeamUpdate",
    "GradeBeamBulkItem",
    "GradeBeamBulkReplace",
]


class GradeBeamCreate(BaseModel):
    """A pour's use of a beam type: which type, and how much."""

    mono_slab_id: UUID
    beam_type_id: UUID
    length_lf: Decimal = Field(..., ge=0, examples=[240])
    notes: str | None = None
    sort_order: int = 0


class GradeBeamUpdate(BaseModel):
    beam_type_id: UUID | None = None
    length_lf: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None


class GradeBeamRead(BaseModel):
    """
    A pour usage, flattened with its type's section so the UI can render a row
    without a second lookup.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mono_slab_id: UUID
    beam_type_id: UUID
    length_lf: Decimal
    notes: str | None = None
    sort_order: int = 0

    # From the type
    label: str | None = None
    kind: BeamKind = "grade_beam"
    width_in: Decimal | None = None
    height_in: Decimal | None = None
    top_bars_count: int | None = None
    top_bars_size: int | None = None
    bottom_bars_count: int | None = None
    bottom_bars_size: int | None = None
    mid_bars_count: int | None = None
    mid_bars_size: int | None = None
    stirrup_size: int | None = None
    stirrup_spacing_in: Decimal | None = None
    l_bars_count: int | None = None
    l_bars_size: int | None = None
    l_bars_spacing_in: Decimal | None = None
    pt_cables_count: int | None = None

    calc_rebar_lb: Decimal | None = None
    calc_pt_cable_lf: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_poly_sf: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class GradeBeamBulkItem(BaseModel):
    """One row of a pour's beam list: a type and a length."""

    beam_type_id: UUID
    length_lf: Decimal = Field(..., ge=0)
    notes: str | None = None
    sort_order: int = 0


class GradeBeamBulkReplace(BaseModel):
    """
    Replace a pour's usages for one kind. Rows with length <= 0 are dropped, so
    clearing a length removes that type from the pour.
    """

    kind: BeamKind = "grade_beam"
    beams: list[GradeBeamBulkItem] = Field(default_factory=list)
