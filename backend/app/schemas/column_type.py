from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ColumnTypeBase(BaseModel):
    # extra="forbid" everywhere below. A bulk save that silently swallowed a
    # misspelled field is how 62,000 lb of pier rebar once came back as zero
    # with a 200 OK.
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, max_length=100)
    description: str | None = None

    qty: int = Field(0, ge=0, description="How many of this column type.")
    mix_design_id: int | None = None

    height_ft: Decimal = Field(0, ge=0)
    length_in: Decimal = Field(0, ge=0)
    width_in: Decimal = Field(0, ge=0)

    # Three vertical sets, because the sheet carries three. A set with no count
    # or no size contributes nothing rather than a zero-weight bar.
    vert1_count: int | None = Field(None, ge=0)
    vert1_size: int | None = Field(None, ge=0, le=20)
    vert2_count: int | None = Field(None, ge=0)
    vert2_size: int | None = Field(None, ge=0, le=20)
    vert3_count: int | None = Field(None, ge=0)
    vert3_size: int | None = Field(None, ge=0, le=20)

    tie_size: int | None = Field(None, ge=0, le=20)
    tie_spacing_in: Decimal | None = Field(None, ge=0)

    dowel_count: int | None = Field(None, ge=0)
    dowel_size: int | None = Field(None, ge=0, le=20)
    dowel_length_ft: Decimal | None = Field(None, ge=0)

    notes: str | None = None
    sort_order: int = 0


class ColumnTypeCreate(ColumnTypeBase):
    section_id: UUID


class ColumnTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    qty: int | None = Field(None, ge=0)
    mix_design_id: int | None = None
    height_ft: Decimal | None = Field(None, ge=0)
    length_in: Decimal | None = Field(None, ge=0)
    width_in: Decimal | None = Field(None, ge=0)
    vert1_count: int | None = Field(None, ge=0)
    vert1_size: int | None = Field(None, ge=0, le=20)
    vert2_count: int | None = Field(None, ge=0)
    vert2_size: int | None = Field(None, ge=0, le=20)
    vert3_count: int | None = Field(None, ge=0)
    vert3_size: int | None = Field(None, ge=0, le=20)
    tie_size: int | None = Field(None, ge=0, le=20)
    tie_spacing_in: Decimal | None = Field(None, ge=0)
    dowel_count: int | None = Field(None, ge=0)
    dowel_size: int | None = Field(None, ge=0, le=20)
    dowel_length_ft: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None


class ColumnTypeRead(ColumnTypeBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    section_id: UUID

    calc_form_sf: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_vert_rebar_lb: Decimal | None = None
    calc_tie_rebar_lb: Decimal | None = None
    calc_dowel_rebar_lb: Decimal | None = None
    calc_total_rebar_lb: Decimal | None = None
    calc_chamfer_lf: Decimal | None = None

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


class ColumnTypeBulkRow(ColumnTypeBase):
    id: UUID | None = None


class ColumnTypeBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[ColumnTypeBulkRow] = Field(default_factory=list)
    delete_missing: bool = False


class ColumnTotals(BaseModel):
    section_id: UUID
    type_count: int = 0
    column_count: int = 0
    total_form_sf: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_vert_rebar_lb: Decimal = Decimal("0")
    total_tie_rebar_lb: Decimal = Decimal("0")
    total_dowel_rebar_lb: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_chamfer_lf: Decimal = Decimal("0")
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_cost_per_unit: Decimal | None = None
    total_sale_per_unit: Decimal | None = None
    cost_per_form_sf: Decimal | None = None


class ColumnTypeBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[ColumnTypeRead] = Field(default_factory=list)
    totals: ColumnTotals | None = None
