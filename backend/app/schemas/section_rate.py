from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SectionRateRead(BaseModel):
    """
    One rate, as this section resolves it — and the whole ladder behind it.

    Every layer is reported, not just the answer. A rate you cannot trace is a
    rate you cannot defend three months later, and the layers are what make
    "$0.42 here where the company says $0.55" a decision rather than a typo.
    """

    key: str
    label: str
    unit: str | None = None
    # A PRICE is frozen on the estimate's price sheet; a RULE is read live.
    # The screen needs the split for the same reason the settings screen does.
    is_price: bool = False
    # WHERE this rate may be set: "section" or "estimate". Chad's policy,
    # 2026-09-04: "each section should be separate from the others for labor
    # ... materials should be standard across the estimate. concrete and
    # materials are quoted per job so should be edited that way."
    #
    # An estimate-level row is shown READ-ONLY here with a pointer to the price
    # sheet, rather than hidden — you still want to see what this section is
    # paying for PT cable, you just do not set it here.
    level: str = "section"

    # What this section actually uses right now, and which rung it came from.
    value: Decimal | None = None
    source: str = "default"          # section | job | assembly | company | default

    # The rungs, each one None when that layer says nothing.
    section_value: Decimal | None = None
    note: str | None = None
    job_value: Decimal | None = None
    assembly_value: Decimal | None = None
    company_value: Decimal | None = None
    default_value: Decimal | None = None

    # True when this section's takeoff actually asked for this key on the last
    # build. A key that is listed only because the assembly names it is shown
    # dimmer: it is available, but nothing on this section reads it today.
    was_read: bool = False


class SectionRatesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_id: UUID
    estimate_id: UUID
    kind: str
    name: str
    rows: list[SectionRateRead] = Field(default_factory=list)
    overridden: int = 0


class SectionRateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal = Field(..., ge=0)
    # Why this section differs. Not required, but the screen asks for it —
    # the quote cards learned that a number without a reason beside it is one
    # nobody can defend later.
    note: str | None = Field(None, max_length=200)
