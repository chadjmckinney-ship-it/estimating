from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BeamKind = Literal["grade_beam", "exposed", "drop"]
BEAM_KINDS = ("grade_beam", "exposed", "drop")


class BeamTypeBase(BaseModel):
    """A section + bar schedule, defined once per estimate."""

    label: str = Field(..., min_length=1, max_length=120, examples=["Beam 1 (type 1)"])
    kind: BeamKind = "grade_beam"
    width_in: Decimal = Field(..., gt=0, examples=[12])
    height_in: Decimal = Field(..., gt=0, examples=[30])
    top_bars_count: int | None = Field(None, ge=0, examples=[2])
    top_bars_size: int | None = Field(None, ge=3, le=11, examples=[5])
    bottom_bars_count: int | None = Field(None, ge=0)
    bottom_bars_size: int | None = Field(None, ge=3, le=11)
    mid_bars_count: int | None = Field(None, ge=0)
    mid_bars_size: int | None = Field(None, ge=3, le=11)
    stirrup_size: int | None = Field(None, ge=3, le=11, examples=[3])
    stirrup_spacing_in: Decimal | None = Field(None, gt=0, examples=[24])
    l_bars_count: int | None = Field(None, ge=0)
    l_bars_size: int | None = Field(None, ge=3, le=11)
    l_bars_spacing_in: Decimal | None = Field(None, gt=0)
    pt_cables_count: int | None = Field(
        None, ge=0, description="Cables through this section (grade_beam only); LF = count × length"
    )
    notes: str | None = None
    sort_order: int = 0


class BeamTypeCreate(BeamTypeBase):
    pass


class BeamTypeUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=120)
    kind: BeamKind | None = None
    width_in: Decimal | None = Field(None, gt=0)
    height_in: Decimal | None = Field(None, gt=0)
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


class BeamTypeRead(BeamTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    estimate_id: UUID
    # Where this type is used, rolled up across the estimate
    pour_count: int = 0
    total_lf: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime
