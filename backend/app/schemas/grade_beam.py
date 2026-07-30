from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BeamKind = Literal["grade_beam", "exposed", "drop"]
BEAM_KINDS = ("grade_beam", "exposed", "drop")


class GradeBeamBase(BaseModel):
    kind: BeamKind = "grade_beam"
    label: str | None = Field(None, examples=["GB Type 1", "Perimeter", "EXP 1"])
    width_in: Decimal = Field(..., gt=0, examples=[12])
    height_in: Decimal = Field(..., gt=0, examples=[24])
    length_lf: Decimal = Field(..., ge=0, examples=[120])
    top_bars_count: int | None = Field(None, ge=0, examples=[2])
    top_bars_size: int | None = Field(None, ge=3, le=11, examples=[5])
    bottom_bars_count: int | None = Field(None, ge=0, examples=[3])
    bottom_bars_size: int | None = Field(None, ge=3, le=11, examples=[5])
    mid_bars_count: int | None = Field(None, ge=0)
    mid_bars_size: int | None = Field(None, ge=3, le=11)
    stirrup_size: int | None = Field(None, ge=3, le=11, examples=[3])
    stirrup_spacing_in: Decimal | None = Field(None, gt=0, examples=[18])
    l_bars_count: int | None = Field(None, ge=0)
    l_bars_size: int | None = Field(None, ge=3, le=11)
    l_bars_spacing_in: Decimal | None = Field(None, gt=0)
    pt_cables_count: int | None = Field(
        None,
        ge=0,
        examples=[2],
        description="PT cables (grade_beam only); LF = count × length",
    )
    notes: str | None = None
    sort_order: int = 0


class GradeBeamCreate(GradeBeamBase):
    mono_slab_id: UUID


class GradeBeamUpdate(BaseModel):
    kind: BeamKind | None = None
    label: str | None = None
    width_in: Decimal | None = Field(None, gt=0)
    height_in: Decimal | None = Field(None, gt=0)
    length_lf: Decimal | None = Field(None, ge=0)
    top_bars_count: int | None = Field(None, ge=0)
    top_bars_size: int | None = Field(None, ge=3, le=11)
    bottom_bars_count: int | None = Field(None, ge=0)
    bottom_bars_size: int | None = Field(None, ge=3, le=11)
    mid_bars_count: int | None = Field(None, ge=0)
    mid_bars_size: int | None = Field(None, ge=3, le=11)
    stirrup_size: int | None = Field(None, ge=3, le=11)
    stirrup_spacing_in: Decimal | None = Field(None, gt=0)
    l_bars_count: int | None = Field(None, ge=0)
    l_bars_size: int | None = Field(None, ge=3, le=11)
    l_bars_spacing_in: Decimal | None = Field(None, gt=0)
    pt_cables_count: int | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None


class GradeBeamRead(GradeBeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mono_slab_id: UUID
    calc_rebar_lb: Decimal | None = None
    calc_pt_cable_lf: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_poly_sf: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class GradeBeamBulkItem(GradeBeamBase):
    """One row in a bulk replace (no mono_slab_id — taken from path)."""

    pass


class GradeBeamBulkReplace(BaseModel):
    """
    Replace beams of one kind on a mono slab pour.
    Incomplete rows (no W/H/L) are omitted by the API.
    """

    kind: BeamKind = "grade_beam"
    beams: list[GradeBeamBulkItem] = Field(default_factory=list)
