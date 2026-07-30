from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EstimateStatus(str, Enum):
    draft = "draft"
    in_review = "in_review"
    final = "final"
    archived = "archived"


class EstimateBase(BaseModel):
    project_id: UUID
    name: str = Field(..., min_length=1, max_length=200, examples=["Mono Slab base"])
    status: EstimateStatus = EstimateStatus.draft
    estimator_id: UUID | None = None
    version: int = Field(1, ge=1)
    waste_concrete: Decimal | None = Field(None, ge=0, le=1, examples=[0.05])
    waste_sand: Decimal | None = Field(None, ge=0, le=1)
    waste_rebar: Decimal | None = Field(None, ge=0, le=1)
    form_percent: Decimal | None = Field(
        None,
        ge=0,
        le=2,
        examples=[0.50],
        description="% of forming (0–1 typical). NULL = system default. Forms only: 2x4/2x6/2x10/ply/masonite.",
    )
    notes: str | None = None


class EstimateCreate(EstimateBase):
    pass


class EstimateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    status: EstimateStatus | None = None
    estimator_id: UUID | None = None
    version: int | None = Field(None, ge=1)
    # Bounds must match EstimateBase/EstimateRead — a value that passes here but
    # fails on read is persisted first, then 500s every GET of this estimate.
    waste_concrete: Decimal | None = Field(None, ge=0, le=1)
    waste_sand: Decimal | None = Field(None, ge=0, le=1)
    waste_rebar: Decimal | None = Field(None, ge=0, le=1)
    form_percent: Decimal | None = Field(None, ge=0, le=2)
    notes: str | None = None


class EstimateRead(EstimateBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    project_name: str | None = None
    estimator_name: str | None = None
