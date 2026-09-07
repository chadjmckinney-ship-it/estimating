from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.bar_sizes import BarSize


class PierGroupBase(BaseModel):
    section_id: UUID
    label: str | None = Field(None, examples=["G", "R"], description="Your grouping tag")
    description: str | None = None
    qty: int = Field(..., ge=0, examples=[46], description="Piers in this group")
    diameter_in: Decimal = Field(..., gt=0, examples=[36])
    base_depth_ft: Decimal = Field(Decimal("0"), ge=0, examples=[16])
    rock_penetration_ft: Decimal = Field(Decimal("0"), ge=0, examples=[8])
    bell_size_in: Decimal | None = Field(None, ge=0)
    mix_design_id: int | None = None

    vert_bars_count: int | None = Field(None, ge=0, examples=[8])
    vert_bars_size: BarSize | None = Field(None, examples=[8])
    tie_size: BarSize | None = Field(None, examples=[3])
    tie_spacing_in: Decimal | None = Field(None, gt=0, examples=[10])
    band_tie_count: int | None = Field(
        None, ge=0, examples=[3],
        description='Confinement ties at the top, as the drawing says it: a COUNT '
                    'at band_spacing_in ("3 #3 stirrups at 3 inches top")',
    )
    band_spacing_in: Decimal | None = Field(None, gt=0, examples=[3])
    dowels_count: int | None = Field(None, ge=0, examples=[4])
    dowels_size: BarSize | None = Field(None, examples=[6])
    dowels_length_ft: Decimal | None = Field(None, ge=0, examples=[8])

    notes: str | None = None
    sort_order: int = 0


class PierGroupCreate(PierGroupBase):
    # extra="forbid" (audit 2026-09-04, P2 #8). This is the assembly it
    # happened on: a bulk save silently swallowed misspelled pier fields and
    # returned zero rebar with a 200 OK. The wall, column and deck schemas got
    # the guard when they were written; the two oldest takeoffs did not.
    model_config = ConfigDict(extra="forbid")


class PierGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    qty: int | None = Field(None, ge=0)
    diameter_in: Decimal | None = Field(None, gt=0)
    base_depth_ft: Decimal | None = Field(None, ge=0)
    rock_penetration_ft: Decimal | None = Field(None, ge=0)
    bell_size_in: Decimal | None = Field(None, ge=0)
    mix_design_id: int | None = None
    vert_bars_count: int | None = Field(None, ge=0)
    vert_bars_size: BarSize | None = None
    tie_size: BarSize | None = None
    tie_spacing_in: Decimal | None = Field(None, gt=0)
    band_tie_count: int | None = Field(None, ge=0)
    band_spacing_in: Decimal | None = Field(None, gt=0)
    dowels_count: int | None = Field(None, ge=0)
    dowels_size: BarSize | None = None
    dowels_length_ft: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None


class PierGroupBulkRow(PierGroupUpdate):
    """One row of a grid save. `id` present = update, absent = create."""

    id: UUID | None = None


class PierGroupBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[PierGroupBulkRow] = Field(default_factory=list, max_length=200)
    delete_missing: bool = Field(
        False,
        description="Delete groups the grid did not send back. Off by default: a "
                    "save that silently drops work is worse than a row the user "
                    "has to delete twice.",
    )


class PierGroupRead(PierGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    calc_total_depth_ft: Decimal | None = None
    calc_total_lf: Decimal | None = None
    calc_shaft_concrete_cy: Decimal | None = None
    calc_bell_concrete_cy: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_tie_count: Decimal | None = None
    calc_vert_rebar_lb: Decimal | None = None
    calc_tie_rebar_lb: Decimal | None = None
    calc_dowel_rebar_lb: Decimal | None = None
    calc_total_rebar_lb: Decimal | None = None
    # NULL means the diameter has no row in pier_drill_rates — the line says so
    # rather than guessing a rate.
    calc_drill_lf_rate: Decimal | None = None
    calc_drill_cost: Decimal | None = None
    calc_direct_cost: Decimal | None = None
    calc_allocated_cost: Decimal | None = None
    calc_equip_fuel: Decimal | None = None
    calc_tax: Decimal | None = None
    calc_cost: Decimal | None = None
    calc_sale: Decimal | None = None
    calc_cost_per_unit: Decimal | None = None
    calc_sale_per_unit: Decimal | None = None
    mix_design_code: str | None = None
    created_at: datetime
    updated_at: datetime


class PierTotals(BaseModel):
    section_id: UUID
    group_count: int = 0
    pier_count: int = 0
    total_lf: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_shaft_concrete_cy: Decimal = Decimal("0")
    total_bell_concrete_cy: Decimal = Decimal("0")
    total_vert_rebar_lb: Decimal = Decimal("0")
    total_tie_rebar_lb: Decimal = Decimal("0")
    total_dowel_rebar_lb: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_tie_count: Decimal = Decimal("0")
    total_drill_cost: Decimal = Decimal("0")
    groups_without_drill_rate: int = 0
    # "quote" when a lump sum priced the drilling, "rates" when pier_drill_rates
    # did. Drilling is the largest line on a pier job, so which one answered is
    # a headline number, not a detail.
    drill_source: str = "rates"
    drill_quote: Decimal | None = None
    drill_quote_note: str | None = None
    # The LF the quote was priced against vs. total_lf above. Stale is true when
    # they differ — or when nothing was stamped, since an unverifiable quote is
    # not a current one.
    drill_quote_lf: Decimal | None = None
    drill_quote_stale: bool = False
    # How the lump was apportioned: "rate_shape" spreads it in proportion to
    # what pier_drill_rates would have charged each group, preserving the cost
    # difference between a 24" and a 42" shaft; "lf" is the flat per-foot
    # fallback used when a diameter has no row to describe that shape.
    drill_quote_basis: str | None = None
    # What the rate table would have charged for the same holes. NULL when any
    # diameter is missing from the table, so a partial figure is never shown
    # next to a full one.
    drill_rate_cost: Decimal | None = None
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_cost_per_unit: Decimal | None = None
    total_sale_per_unit: Decimal | None = None


class PierGroupBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[PierGroupRead] = Field(default_factory=list)
    totals: PierTotals | None = None


class PierDrillRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    diameter_in: Decimal
    drill_per_lf: Decimal
    casing_per_lf: Decimal
    deduct_per_lf: Decimal
    note: str | None = None
