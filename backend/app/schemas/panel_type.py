from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.bar_sizes import BarSize


class PanelTypeBase(BaseModel):
    # extra="forbid" everywhere below, the rule every takeoff schema follows:
    # a bulk save that swallowed a misspelled field once returned 62,000 lb of
    # pier rebar as zero with a 200 OK.
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, max_length=100)
    description: str | None = None

    qty: int = Field(0, ge=0, description="How many of this panel type.")
    mix_design_id: int | None = None

    length_ft: Decimal = Field(0, ge=0)
    thickness_in: Decimal = Field(0, ge=0)
    # Elevations, as the tab types them — a bottom below grade is negative.
    top_el_ft: Decimal = 0
    bot_el_ft: Decimal = 0

    # Four openings per panel, each L x W (sql/077). A slot with no length or
    # no width is no opening.
    open1_len_ft: Decimal | None = Field(None, ge=0)
    open1_wide_ft: Decimal | None = Field(None, ge=0)
    open2_len_ft: Decimal | None = Field(None, ge=0)
    open2_wide_ft: Decimal | None = Field(None, ge=0)
    open3_len_ft: Decimal | None = Field(None, ge=0)
    open3_wide_ft: Decimal | None = Field(None, ge=0)
    open4_len_ft: Decimal | None = Field(None, ge=0)
    open4_wide_ft: Decimal | None = Field(None, ge=0)

    horiz_spacing_in: Decimal | None = Field(None, ge=0)
    horiz_size: BarSize | None = None
    horiz_mats: int | None = Field(None, ge=0)
    vert_spacing_in: Decimal | None = Field(None, ge=0)
    vert_size: BarSize | None = None
    vert_mats: int | None = Field(None, ge=0)
    edge_bar_count: int | None = Field(None, ge=0)
    edge_bar_size: BarSize | None = None
    corner_bar_count: int | None = Field(None, ge=0)
    corner_bar_size: BarSize | None = None

    notes: str | None = None
    sort_order: int = 0

    # A grid sends an empty cell as null, and on a QUANTITY that is a zero —
    # a schedule row still being filled in — not a type error (the rule is
    # spelled out in schemas/wall_run.py). The bulk route still refuses a new
    # row with no length or no height.
    @field_validator("qty", "length_ft", "thickness_in", "top_el_ft", "bot_el_ft", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class PanelTypeCreate(PanelTypeBase):
    section_id: UUID


class PanelTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    qty: int | None = Field(None, ge=0)
    mix_design_id: int | None = None
    length_ft: Decimal | None = Field(None, ge=0)
    thickness_in: Decimal | None = Field(None, ge=0)
    top_el_ft: Decimal | None = None
    bot_el_ft: Decimal | None = None
    open1_len_ft: Decimal | None = Field(None, ge=0)
    open1_wide_ft: Decimal | None = Field(None, ge=0)
    open2_len_ft: Decimal | None = Field(None, ge=0)
    open2_wide_ft: Decimal | None = Field(None, ge=0)
    open3_len_ft: Decimal | None = Field(None, ge=0)
    open3_wide_ft: Decimal | None = Field(None, ge=0)
    open4_len_ft: Decimal | None = Field(None, ge=0)
    open4_wide_ft: Decimal | None = Field(None, ge=0)
    horiz_spacing_in: Decimal | None = Field(None, ge=0)
    horiz_size: BarSize | None = None
    horiz_mats: int | None = Field(None, ge=0)
    vert_spacing_in: Decimal | None = Field(None, ge=0)
    vert_size: BarSize | None = None
    vert_mats: int | None = Field(None, ge=0)
    edge_bar_count: int | None = Field(None, ge=0)
    edge_bar_size: BarSize | None = None
    corner_bar_count: int | None = Field(None, ge=0)
    corner_bar_size: BarSize | None = None
    notes: str | None = None
    sort_order: int | None = None

    # Same rule on a single-row PATCH: these five are NOT NULL in the table.
    @field_validator("qty", "length_ft", "thickness_in", "top_el_ft", "bot_el_ft", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class PanelTypeRead(PanelTypeBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    section_id: UUID

    calc_height_ft: Decimal | None = None
    calc_sf_each: Decimal | None = None
    calc_sf: Decimal | None = None
    calc_opening_sf: Decimal | None = None
    calc_opening_lf: Decimal | None = None
    calc_perimeter_lf: Decimal | None = None
    calc_bottom_lf: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_steel_each_lb: Decimal | None = None
    calc_total_rebar_lb: Decimal | None = None

    calc_direct_cost: Decimal | None = None
    calc_allocated_cost: Decimal | None = None
    calc_equip_fuel: Decimal | None = None
    calc_tax: Decimal | None = None
    calc_cost: Decimal | None = None
    calc_sale: Decimal | None = None
    # Per SF — the unit the section sells in.
    calc_cost_per_unit: Decimal | None = None
    calc_sale_per_unit: Decimal | None = None
    # Per panel — the tab's X column, derived on read from the type's cost.
    calc_cost_per_panel: Decimal | None = None
    calc_sale_per_panel: Decimal | None = None

    created_at: datetime
    updated_at: datetime


class PanelTypeBulkRow(PanelTypeBase):
    id: UUID | None = None


class PanelTypeBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[PanelTypeBulkRow] = Field(default_factory=list)
    delete_missing: bool = False


class PanelTotals(BaseModel):
    section_id: UUID
    type_count: int = 0
    panel_count: int = 0
    total_sf: Decimal = Decimal("0")
    total_opening_sf: Decimal = Decimal("0")
    total_opening_lf: Decimal = Decimal("0")
    total_perimeter_lf: Decimal = Decimal("0")
    total_bottom_lf: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_cost_per_unit: Decimal | None = None
    total_sale_per_unit: Decimal | None = None
    cost_per_panel: Decimal | None = None
    sale_per_panel: Decimal | None = None


class PanelTypeBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[PanelTypeRead] = Field(default_factory=list)
    totals: PanelTotals | None = None
