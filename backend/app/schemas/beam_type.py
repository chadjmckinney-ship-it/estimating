from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.bar_sizes import BarSize

BeamKind = Literal["grade_beam", "exposed", "drop", "brick_ledge"]
BEAM_KINDS = ("grade_beam", "exposed", "drop", "brick_ledge")


class BeamTypeBase(BaseModel):
    """A section + bar schedule, defined once per estimate."""

    label: str = Field(..., min_length=1, max_length=120, examples=["Beam 1 (type 1)"])
    kind: BeamKind = "grade_beam"
    # ge=0 rather than gt=0: a brick ledge that does not widen the beam is 0 x 0
    # and exists only to be formed. The database still requires > 0 for every
    # other kind (sql/028).
    width_in: Decimal = Field(..., ge=0, examples=[12])
    height_in: Decimal = Field(..., ge=0, examples=[30])
    form_face_in: Decimal | None = Field(
        None, ge=0,
        description="Brick ledge: depth that gets ply-faced. Blank = the section height.",
        examples=[8],
    )
    top_bars_count: int | None = Field(None, ge=0, examples=[2])
    top_bars_size: BarSize | None = Field(None, examples=[5])
    bottom_bars_count: int | None = Field(None, ge=0)
    bottom_bars_size: BarSize | None = None
    mid_bars_count: int | None = Field(None, ge=0)
    mid_bars_size: BarSize | None = None
    stirrup_size: BarSize | None = Field(None, examples=[3])
    stirrup_spacing_in: Decimal | None = Field(None, gt=0, examples=[24])
    l_bars_count: int | None = Field(None, ge=0)
    l_bars_size: BarSize | None = None
    l_bars_spacing_in: Decimal | None = Field(None, gt=0)
    pt_cables_count: int | None = Field(
        None, ge=0, description="Cables through this section (grade_beam only); LF = count × length"
    )
    notes: str | None = None
    sort_order: int = 0


class BeamTypeCreate(BeamTypeBase):
    # extra="forbid" (audit 2026-09-04, P2 #8): a misspelled field is a 422,
    # not a silent 200. Editing a type moves every pour that uses it, so a
    # field that quietly did not land would be wrong on all of them at once.
    model_config = ConfigDict(extra="forbid")


class BeamTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, min_length=1, max_length=120)
    kind: BeamKind | None = None
    width_in: Decimal | None = Field(None, ge=0)
    height_in: Decimal | None = Field(None, ge=0)
    form_face_in: Decimal | None = Field(None, ge=0)
    top_bars_count: int | None = Field(None, ge=0)
    top_bars_size: BarSize | None = None
    bottom_bars_count: int | None = Field(None, ge=0)
    bottom_bars_size: BarSize | None = None
    mid_bars_count: int | None = Field(None, ge=0)
    mid_bars_size: BarSize | None = None
    stirrup_size: BarSize | None = None
    stirrup_spacing_in: Decimal | None = Field(None, gt=0)
    l_bars_count: int | None = Field(None, ge=0)
    l_bars_size: BarSize | None = None
    l_bars_spacing_in: Decimal | None = Field(None, gt=0)
    pt_cables_count: int | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None


class BeamTypeBulkRow(BeamTypeBase):
    """
    One row of the grade-beams modal's schedule: an existing type (id) or a
    new one. On an existing type only the fields SENT are written — the modal
    shows a subset (no notes, no L bars, no ledge face), and a save from it
    must not blank what the type editor set.
    """
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None


class BeamTypeBulk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[BeamTypeBulkRow] = Field(..., max_length=200)


class BeamTypeRead(BeamTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    section_id: UUID
    # Where this type is used and what it contributes, across the estimate
    pour_count: int = 0
    total_lf: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_poly_sf: Decimal = Decimal("0")
    total_pt_cable_lf: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime


class BeamTypeBulkResult(BaseModel):
    created: int
    updated: int
    rows: list[BeamTypeRead]
