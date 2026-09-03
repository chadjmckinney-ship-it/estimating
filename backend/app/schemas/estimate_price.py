from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EstimatePriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    estimate_id: UUID
    kind: str
    scope: str | None = None
    ref_id: int | None = None
    ref_key: str | None = None
    label: str
    unit: str | None = None
    category: str | None = None
    # What the master list said when this row was pulled, and what this job
    # pays. They differ when a person edited the row (is_edited) — or when the
    # master moved and the row is edited, in which case the drift check has
    # refreshed catalog_value and left value alone.
    catalog_value: Decimal | None = None
    value: Decimal
    is_edited: bool = False
    note: str | None = None
    pulled_at: datetime
    updated_at: datetime


class EstimatePriceUpdate(BaseModel):
    """
    Change what this job pays for one item.

    `reset` puts the master price back and clears `is_edited`. Setting `value`
    to the master number by hand does NOT clear it — that is still a decision.
    """

    model_config = ConfigDict(extra="forbid")

    # ≥ 0 here; whether zero is allowed depends on the row (a rate may be
    # zero, a mix / material / machine may not) and `set_price` decides.
    value: Decimal | None = Field(None, ge=0)
    note: str | None = None
    reset: bool = False


class PullResultRead(BaseModel):
    """What a pull did, or — dry run — what it would do."""

    estimate_id: str
    applied: bool
    new: list[dict[str, Any]] = Field(default_factory=list)
    changed: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    unpriced: list[dict[str, Any]] = Field(default_factory=list)
    retired: list[dict[str, Any]] = Field(default_factory=list)
    unchanged: int = 0
    drift: int = 0


class EstimatePriceSheetRead(BaseModel):
    """The whole sheet, plus what has moved on the master list since the pull."""

    estimate_id: UUID
    rows: list[EstimatePriceRead] = Field(default_factory=list)
    edited: int = 0
    pulled_at: datetime | None = None
    drift: PullResultRead
