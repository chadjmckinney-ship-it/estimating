from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Shape = Literal["round", "block", "slab", "box"]


class MiscItemBase(BaseModel):
    # extra="forbid", the rule every takeoff schema follows.
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(None, max_length=20)
    description: str | None = None
    shape: Shape = "round"
    unit: str = Field("EA", max_length=10)
    qty: Decimal = Field(0, ge=0)

    unit_sale: Decimal | None = Field(None, ge=0)
    labor_per_unit: Decimal = Field(0, ge=0)
    subcontracted: bool = True

    pours_concrete: bool = True
    mix_design_id: int | None = None
    dim_a: Decimal | None = Field(None, ge=0)
    dim_b: Decimal | None = Field(None, ge=0)
    dim_c: Decimal | None = Field(None, ge=0)
    concrete_waste: Decimal = Field(0, ge=0, le=1)

    steel_lb_per_cy: Decimal = Field(0, ge=0)
    steel_lb_per_in_ft: Decimal = Field(0, ge=0)
    steel_lb_per_unit: Decimal = Field(0, ge=0)

    forms_pct_of_sale: Decimal = Field(0, ge=0, le=1)
    forms_per_unit: Decimal = Field(0, ge=0)
    forms_per_face_sf: Decimal = Field(0, ge=0)
    forms_pct_of_concrete: Decimal = Field(0, ge=0, le=5)
    super_pct_of_labor: Decimal = Field(0, ge=0, le=5)
    equip_per_unit: Decimal = Field(0, ge=0)
    equip_pct_of_labor: Decimal = Field(0, ge=0, le=5)
    equip_min: Decimal = Field(0, ge=0)

    notes: str | None = None
    sort_order: int = 0

    # A grid sends an empty cell as null; on a quantity or a factor that is a
    # zero, not a type error (the rule is spelled out in schemas/wall_run.py).
    @field_validator(
        "qty", "labor_per_unit", "concrete_waste", "steel_lb_per_cy", "steel_lb_per_in_ft",
        "steel_lb_per_unit", "forms_pct_of_sale", "forms_per_unit", "forms_per_face_sf",
        "forms_pct_of_concrete", "super_pct_of_labor", "equip_per_unit", "equip_pct_of_labor",
        "equip_min", mode="before",
    )
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v

    @field_validator("shape", "unit", "subcontracted", "pours_concrete", mode="before")
    @classmethod
    def _blank_is_default(cls, v, info):
        if v is None or v == "":
            return {"shape": "round", "unit": "EA", "subcontracted": True, "pours_concrete": True}[info.field_name]
        return v


class MiscItemCreate(MiscItemBase):
    section_id: UUID


class MiscItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = None
    description: str | None = None
    shape: Shape | None = None
    unit: str | None = None
    qty: Decimal | None = Field(None, ge=0)
    unit_sale: Decimal | None = Field(None, ge=0)
    labor_per_unit: Decimal | None = Field(None, ge=0)
    subcontracted: bool | None = None
    pours_concrete: bool | None = None
    mix_design_id: int | None = None
    dim_a: Decimal | None = Field(None, ge=0)
    dim_b: Decimal | None = Field(None, ge=0)
    dim_c: Decimal | None = Field(None, ge=0)
    concrete_waste: Decimal | None = Field(None, ge=0, le=1)
    steel_lb_per_cy: Decimal | None = Field(None, ge=0)
    steel_lb_per_in_ft: Decimal | None = Field(None, ge=0)
    steel_lb_per_unit: Decimal | None = Field(None, ge=0)
    forms_pct_of_sale: Decimal | None = Field(None, ge=0, le=1)
    forms_per_unit: Decimal | None = Field(None, ge=0)
    forms_per_face_sf: Decimal | None = Field(None, ge=0)
    forms_pct_of_concrete: Decimal | None = Field(None, ge=0, le=5)
    super_pct_of_labor: Decimal | None = Field(None, ge=0, le=5)
    equip_per_unit: Decimal | None = Field(None, ge=0)
    equip_pct_of_labor: Decimal | None = Field(None, ge=0, le=5)
    equip_min: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None

    @field_validator("qty", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class MiscItemRead(MiscItemBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    section_id: UUID

    calc_concrete_cy: Decimal | None = None
    calc_steel_lb: Decimal | None = None
    calc_face_sf: Decimal | None = None
    calc_sale: Decimal | None = None
    calc_concrete_cost: Decimal | None = None
    calc_steel_cost: Decimal | None = None
    calc_forms_cost: Decimal | None = None
    calc_labor_cost: Decimal | None = None
    calc_super_cost: Decimal | None = None
    calc_equip_cost: Decimal | None = None
    calc_margin: Decimal | None = None

    calc_direct_cost: Decimal | None = None
    calc_allocated_cost: Decimal | None = None
    calc_equip_fuel: Decimal | None = None
    calc_tax: Decimal | None = None
    calc_cost: Decimal | None = None
    calc_cost_per_unit: Decimal | None = None
    calc_sale_per_unit: Decimal | None = None

    created_at: datetime
    updated_at: datetime


class MiscItemBulkRow(MiscItemBase):
    id: UUID | None = None


class MiscItemBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[MiscItemBulkRow] = Field(default_factory=list)
    delete_missing: bool = False


class MiscTotals(BaseModel):
    section_id: UUID
    row_count: int = 0
    item_count: int = 0
    total_qty: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_steel_lb: Decimal = Decimal("0")
    total_concrete_cost: Decimal = Decimal("0")
    total_steel_cost: Decimal = Decimal("0")
    total_forms_cost: Decimal = Decimal("0")
    total_labor_cost: Decimal = Decimal("0")
    total_sub_labor_cost: Decimal = Decimal("0")
    total_super_cost: Decimal = Decimal("0")
    total_equip_cost: Decimal = Decimal("0")
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_margin: Decimal | None = None
    sale_at_markup: Decimal = Decimal("0")


class MiscItemBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[MiscItemRead] = Field(default_factory=list)
    totals: MiscTotals | None = None
