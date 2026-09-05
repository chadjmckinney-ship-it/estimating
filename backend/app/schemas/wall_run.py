from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WallRunBase(BaseModel):
    # extra="forbid" everywhere below. A bulk save that silently swallowed a
    # misspelled field is how 62,000 lb of pier rebar once came back as zero
    # with a 200 OK.
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, max_length=100)
    description: str | None = None
    backfill: bool = Field(
        False, description="Drives sand, excavation, backfill and the french drain."
    )
    mix_design_id: int | None = Field(
        None, description="The WALL's mix. The footing has its own below, else the section's, else this."
    )
    footing_mix_design_id: int | None = Field(
        None,
        description="This footing's mix (sql/062). Blank: the section's footing mix, then the wall's.",
    )

    length_ft: Decimal = Field(0, ge=0)
    wall_thick_in: Decimal = Field(0, ge=0)
    wall_height_in: Decimal = Field(0, ge=0)

    horiz_spacing_in: Decimal | None = Field(None, ge=0)
    horiz_size: int | None = Field(None, ge=0, le=20)
    horiz_mats: int | None = Field(None, ge=0, description="Faces — 2 is both.")
    vert_spacing_in: Decimal | None = Field(None, ge=0)
    vert_size: int | None = Field(None, ge=0, le=20)
    vert_mats: int | None = Field(None, ge=0)

    ftg_width_in: Decimal = Field(0, ge=0)
    ftg_thick_in: Decimal = Field(0, ge=0)
    # Two mats (sql/059), each its own bar set. A mat with no spacing or no
    # size contributes nothing; a one-mat footing leaves the top blank.
    ftg_bot_spacing_in: Decimal | None = Field(None, ge=0)
    ftg_bot_size: int | None = Field(None, ge=0, le=20)
    ftg_top_spacing_in: Decimal | None = Field(None, ge=0)
    ftg_top_size: int | None = Field(None, ge=0, le=20)

    notes: str | None = None
    sort_order: int = 0

    # A grid sends an empty cell as null, and on a QUANTITY that is a zero —
    # no footing under this wall — not a type error. A default only applies
    # when the key is absent, so until 2026-09-05 a blank footing width was a
    # 422 ("Decimal input should be an integer, float, string or Decimal
    # object", no field named) and Chad typed a 0 into every footing box of
    # every wall that had none. Blank means none. The bulk route still refuses
    # a NEW row with no length, so a blank that mattered is still caught — and
    # api.js now names the cell.
    @field_validator(
        "length_ft", "wall_thick_in", "wall_height_in", "ftg_width_in", "ftg_thick_in",
        mode="before",
    )
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class WallRunCreate(WallRunBase):
    section_id: UUID


class WallRunUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    backfill: bool | None = None
    mix_design_id: int | None = None
    footing_mix_design_id: int | None = None
    length_ft: Decimal | None = Field(None, ge=0)
    wall_thick_in: Decimal | None = Field(None, ge=0)
    wall_height_in: Decimal | None = Field(None, ge=0)
    horiz_spacing_in: Decimal | None = Field(None, ge=0)
    horiz_size: int | None = Field(None, ge=0, le=20)
    horiz_mats: int | None = Field(None, ge=0)
    vert_spacing_in: Decimal | None = Field(None, ge=0)
    vert_size: int | None = Field(None, ge=0, le=20)
    vert_mats: int | None = Field(None, ge=0)
    ftg_width_in: Decimal | None = Field(None, ge=0)
    ftg_thick_in: Decimal | None = Field(None, ge=0)
    ftg_bot_spacing_in: Decimal | None = Field(None, ge=0)
    ftg_bot_size: int | None = Field(None, ge=0, le=20)
    ftg_top_spacing_in: Decimal | None = Field(None, ge=0)
    ftg_top_size: int | None = Field(None, ge=0, le=20)
    notes: str | None = None
    sort_order: int | None = None

    # Same rule on a single-row PATCH: these five are NOT NULL in the table,
    # so an explicit null here was an IntegrityError on the way in.
    @field_validator(
        "length_ft", "wall_thick_in", "wall_height_in", "ftg_width_in", "ftg_thick_in",
        mode="before",
    )
    @classmethod
    def _blank_is_zero(cls, v):
        return 0 if v is None else v


class WallRunRead(WallRunBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    section_id: UUID

    calc_form_ff: Decimal | None = None
    calc_footing_sf: Decimal | None = None
    calc_wall_concrete_cy: Decimal | None = None
    calc_footing_concrete_cy: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_horiz_rebar_lb: Decimal | None = None
    calc_vert_rebar_lb: Decimal | None = None
    calc_footing_rebar_lb: Decimal | None = None
    calc_lap_rebar_lb: Decimal | None = None
    calc_total_rebar_lb: Decimal | None = None
    calc_sand_cy: Decimal | None = None
    calc_excavate_cy: Decimal | None = None
    calc_backfill_cy: Decimal | None = None
    calc_drain_lf: Decimal | None = None

    # The wall/footing split (sql/042) — each on its own driver.
    calc_wall_cost: Decimal | None = None
    calc_wall_sale: Decimal | None = None
    calc_wall_cost_per_ff: Decimal | None = None
    calc_wall_sale_per_ff: Decimal | None = None
    calc_footing_cost: Decimal | None = None
    calc_footing_sale: Decimal | None = None
    calc_footing_cost_per_sf: Decimal | None = None
    calc_footing_sale_per_sf: Decimal | None = None

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


class WallRunBulkRow(WallRunBase):
    id: UUID | None = None


class WallRunBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[WallRunBulkRow] = Field(default_factory=list)
    delete_missing: bool = False


class WallTotals(BaseModel):
    section_id: UUID
    run_count: int = 0
    total_length_ft: Decimal = Decimal("0")
    total_form_ff: Decimal = Decimal("0")
    total_footing_sf: Decimal = Decimal("0")
    total_wall_concrete_cy: Decimal = Decimal("0")
    total_footing_concrete_cy: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_horiz_rebar_lb: Decimal = Decimal("0")
    total_vert_rebar_lb: Decimal = Decimal("0")
    total_footing_rebar_lb: Decimal = Decimal("0")
    total_lap_rebar_lb: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_sand_cy: Decimal = Decimal("0")
    total_excavate_cy: Decimal = Decimal("0")
    total_backfill_cy: Decimal = Decimal("0")
    total_drain_lf: Decimal = Decimal("0")
    total_wall_cost: Decimal = Decimal("0")
    total_wall_sale: Decimal = Decimal("0")
    total_footing_cost: Decimal = Decimal("0")
    total_footing_sale: Decimal = Decimal("0")
    wall_cost_per_ff: Decimal | None = None
    wall_sale_per_ff: Decimal | None = None
    footing_cost_per_sf: Decimal | None = None
    footing_sale_per_sf: Decimal | None = None
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_cost_per_unit: Decimal | None = None
    total_sale_per_unit: Decimal | None = None


class WallRunBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[WallRunRead] = Field(default_factory=list)
    totals: WallTotals | None = None
