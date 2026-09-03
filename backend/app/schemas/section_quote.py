from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SectionQuoteWrite(BaseModel):
    """
    Write a quote. `unit` decides everything downstream: LS is a lump that gets
    spread and can go stale, anything else is a unit price that replaces a
    catalog rate and cannot.
    """

    # extra="forbid" on purpose. A bulk save that silently ignored a misspelled
    # field is how 62,000 lb of pier rebar came back as zero without an error —
    # on a money field that lesson is worth a 422.
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(..., ge=0, description="0 clears the quote.")
    unit: str = Field("LS", description="LS | TON | CWT | LB | SF")
    note: str | None = Field(
        None,
        max_length=1000,
        description="Who quoted it and what it excludes — casing, rock, mobilization.",
    )


class SectionQuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    label: str
    amount: Decimal
    unit: str
    note: str | None = None
    # The takeoff the quote was priced against, and the takeoff now. Both in
    # `baseline_unit` — LF drilled, lb of steel, SF of PT.
    baseline_qty: Decimal | None = None
    baseline_unit: str | None = None
    current_qty: Decimal | None = None
    # True only for a lump priced against a takeoff that has since moved, or one
    # with no recorded baseline at all. A unit price is never stale.
    stale: bool = False

    # What this quote charges for the package against what the catalog would
    # (sql/046). Shown on every quote; `catalog_verdict` is what decides whether
    # the card warns.
    #
    #   None            no honest comparison — no takeoff, or no catalog price.
    #                   Deliberately NOT "ok": "could not check" and "checked
    #                   and fine" are different states.
    #   "ok"            inside the band.
    #   "far_below"     at or under 0.25x catalog — the $0.65 LS shape.
    #   "far_above"     over 4x — a rate typed where a lump belongs.
    quoted_total: Decimal | None = None
    catalog_total: Decimal | None = None
    catalog_ratio: Decimal | None = None
    catalog_verdict: str | None = None


class SectionQuoteRow(SectionQuoteRead):
    """The stored row, for the quotes endpoint's own responses."""

    id: UUID
    section_id: UUID
    created_at: datetime
    updated_at: datetime
