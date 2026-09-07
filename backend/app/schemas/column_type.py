from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.bar_sizes import BarSize


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
    formed_faces: int = Field(
        4,
        ge=2,
        le=4,
        description=(
            "Faces actually formed: 4 free-standing column (2L+2W), "
            "3 pilaster on a built wall (L+2W), 2 monolithic with it (2W). "
            "The unformed face is always an L face — enter L along the wall."
        ),
    )

    # Three vertical sets, because the sheet carries three. A set with no count
    # or no size contributes nothing rather than a zero-weight bar.
    vert1_count: int | None = Field(None, ge=0)
    vert1_size: BarSize | None = None
    vert2_count: int | None = Field(None, ge=0)
    vert2_size: BarSize | None = None
    vert3_count: int | None = Field(None, ge=0)
    vert3_size: BarSize | None = None

    tie_size: BarSize | None = None
    tie_spacing_in: Decimal | None = Field(None, ge=0)

    dowel_count: int | None = Field(None, ge=0)
    dowel_size: BarSize | None = None
    dowel_length_ft: Decimal | None = Field(None, ge=0)

    notes: str | None = None
    sort_order: int = 0

    # A grid sends an empty cell as null, and on a QUANTITY that is a zero —
    # a schedule row still being filled in — not a type error. A default only
    # applies when the key is absent, so an explicit null was a 422 that named
    # no field (the wall grid's "0 in every footing box", 2026-09-05; the rule
    # is spelled out in schemas/wall_run.py). A blank face count is the
    # default, a free-standing column. The bulk route still refuses a new
    # row with no height.
    @field_validator("qty", "height_ft", "length_in", "width_in", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v

    @field_validator("formed_faces", mode="before")
    @classmethod
    def _blank_faces_is_four(cls, v):
        return 4 if v is None else v


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
    formed_faces: int | None = Field(None, ge=2, le=4)
    vert1_count: int | None = Field(None, ge=0)
    vert1_size: BarSize | None = None
    vert2_count: int | None = Field(None, ge=0)
    vert2_size: BarSize | None = None
    vert3_count: int | None = Field(None, ge=0)
    vert3_size: BarSize | None = None
    tie_size: BarSize | None = None
    tie_spacing_in: Decimal | None = Field(None, ge=0)
    dowel_count: int | None = Field(None, ge=0)
    dowel_size: BarSize | None = None
    dowel_length_ft: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None

    # Same rule on a single-row PATCH: these five are NOT NULL in the table.
    @field_validator("qty", "height_ft", "length_in", "width_in", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v

    @field_validator("formed_faces", mode="before")
    @classmethod
    def _blank_faces_is_four(cls, v):
        return 4 if v is None else v


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
