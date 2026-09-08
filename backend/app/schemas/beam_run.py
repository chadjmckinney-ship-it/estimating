from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.bar_sizes import BarSize

# The quantity columns that are NOT NULL in the table: a blank grid cell is a
# zero on these, the wall-run rule (2026-09-05), not a 422.
_QUANTITIES = (
    "length_ft", "width_in", "height_in",
    "top_bars_count", "bottom_bars_count", "mid_bars_count", "pilaster_count",
)


class BeamRunBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, max_length=100)
    description: str | None = None
    mix_design_id: int | None = Field(None, description="This beam's mix. Blank is unpriced, not free.")

    length_ft: Decimal = Field(0, ge=0)
    width_in: Decimal = Field(0, ge=0)
    height_in: Decimal = Field(0, ge=0)

    top_bars_count: int = Field(0, ge=0)
    top_bars_size: BarSize | None = None
    bottom_bars_count: int = Field(0, ge=0)
    bottom_bars_size: BarSize | None = None
    # The tab's M column counts mid bars per side; the formula doubles them.
    mid_bars_count: int = Field(0, ge=0, description="Per side — the sheet doubles them")
    mid_bars_size: BarSize | None = None
    stirrup_size: BarSize | None = None
    stirrup_spacing_in: Decimal | None = Field(None, ge=0)
    # L bars along the beam at a spacing, each of a length (the tab's Q:S).
    l_bars_size: BarSize | None = None
    l_bars_spacing_in: Decimal | None = Field(None, ge=0)
    l_bars_length_ft: Decimal | None = Field(None, ge=0)

    pilaster_count: int = Field(0, ge=0)
    pilaster_length_in: Decimal | None = Field(None, ge=0)
    pilaster_width_in: Decimal | None = Field(None, ge=0)

    notes: str | None = None
    sort_order: int = 0

    @field_validator(*_QUANTITIES, mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class BeamRunCreate(BeamRunBase):
    section_id: UUID


class BeamRunUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    mix_design_id: int | None = None
    length_ft: Decimal | None = Field(None, ge=0)
    width_in: Decimal | None = Field(None, ge=0)
    height_in: Decimal | None = Field(None, ge=0)
    top_bars_count: int | None = Field(None, ge=0)
    top_bars_size: BarSize | None = None
    bottom_bars_count: int | None = Field(None, ge=0)
    bottom_bars_size: BarSize | None = None
    mid_bars_count: int | None = Field(None, ge=0)
    mid_bars_size: BarSize | None = None
    stirrup_size: BarSize | None = None
    stirrup_spacing_in: Decimal | None = Field(None, ge=0)
    l_bars_size: BarSize | None = None
    l_bars_spacing_in: Decimal | None = Field(None, ge=0)
    l_bars_length_ft: Decimal | None = Field(None, ge=0)
    pilaster_count: int | None = Field(None, ge=0)
    pilaster_length_in: Decimal | None = Field(None, ge=0)
    pilaster_width_in: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None

    @field_validator(*_QUANTITIES, mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class BeamRunRead(BeamRunBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    section_id: UUID

    calc_total_rebar_lb: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_contact_ff: Decimal | None = None
    calc_face_ff: Decimal | None = None
    calc_pilaster_ff: Decimal | None = None
    calc_excavate_cy: Decimal | None = None
    calc_backfill_cy: Decimal | None = None

    calc_direct_cost: Decimal | None = None
    calc_allocated_cost: Decimal | None = None
    calc_equip_fuel: Decimal | None = None
    calc_tax: Decimal | None = None
    calc_cost: Decimal | None = None
    calc_sale: Decimal | None = None
    calc_cost_per_unit: Decimal | None = None
    calc_sale_per_unit: Decimal | None = None

    created_at: datetime
    updated_at: datetime


class BeamRunBulkRow(BeamRunBase):
    id: UUID | None = None


class BeamRunBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[BeamRunBulkRow] = Field(default_factory=list)
    delete_missing: bool = False


class BeamTotals(BaseModel):
    section_id: UUID
    run_count: int = 0
    pilaster_count: int = 0
    total_length_ft: Decimal = Decimal("0")
    total_contact_ff: Decimal = Decimal("0")
    total_face_ff: Decimal = Decimal("0")
    total_pilaster_ff: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_excavate_cy: Decimal = Decimal("0")
    total_backfill_cy: Decimal = Decimal("0")
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    # Per LF — the unit both kinds sell in (Chad, 2026-09-07).
    total_cost_per_unit: Decimal | None = None
    total_sale_per_unit: Decimal | None = None
    # Per face foot — the sheet's own C40, kept beside it.
    cost_per_ff: Decimal | None = None
    sale_per_ff: Decimal | None = None


class BeamRunBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[BeamRunRead] = Field(default_factory=list)
    totals: BeamTotals | None = None
