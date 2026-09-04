from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeckLevelBeamBase(BaseModel):
    """One beam type and how much of it runs through a level."""

    model_config = ConfigDict(extra="forbid")

    beam_type_id: UUID
    length_lf: Decimal = Field(0, ge=0)
    notes: str | None = None
    sort_order: int = 0


class DeckLevelBeamRead(DeckLevelBeamBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    deck_level_id: UUID
    calc_rebar_lb: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_form_ff: Decimal | None = None


class DeckLevelBase(BaseModel):
    # extra="forbid" everywhere below. A bulk save that silently swallowed a
    # misspelled field is how 62,000 lb of pier rebar once came back as zero
    # with a 200 OK.
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, max_length=100)
    description: str | None = None

    area_sf: Decimal = Field(0, ge=0, description="The section's unit, and its allocation basis.")
    thickness_in: Decimal = Field(0, ge=0)
    has_cable: bool = Field(
        False, description="Post-tensioned? PT area is the levels that carry cable."
    )
    mix_design_id: int | None = None
    perm_edge_lf: Decimal = Field(
        0, ge=0, description="Drives the edge rail labor and every lumber line."
    )

    # A mat with no size or no spacing contributes nothing, rather than a
    # zero-weight bar over the whole deck.
    top_bar_size: int | None = Field(None, ge=0, le=20)
    top_bar_spacing_in: Decimal | None = Field(None, ge=0)
    bot_bar_size: int | None = Field(None, ge=0, le=20)
    bot_bar_spacing_in: Decimal | None = Field(None, ge=0)

    mesh_sf: Decimal = Field(0, ge=0)
    stud_rail_lb: Decimal = Field(0, ge=0)
    carton_form_sf: Decimal = Field(0, ge=0)

    notes: str | None = None
    sort_order: int = 0


class DeckLevelCreate(DeckLevelBase):
    section_id: UUID
    beams: list[DeckLevelBeamBase] = Field(default_factory=list)


class DeckLevelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    area_sf: Decimal | None = Field(None, ge=0)
    thickness_in: Decimal | None = Field(None, ge=0)
    has_cable: bool | None = None
    mix_design_id: int | None = None
    perm_edge_lf: Decimal | None = Field(None, ge=0)
    top_bar_size: int | None = Field(None, ge=0, le=20)
    top_bar_spacing_in: Decimal | None = Field(None, ge=0)
    bot_bar_size: int | None = Field(None, ge=0, le=20)
    bot_bar_spacing_in: Decimal | None = Field(None, ge=0)
    mesh_sf: Decimal | None = Field(None, ge=0)
    stud_rail_lb: Decimal | None = Field(None, ge=0)
    carton_form_sf: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    sort_order: int | None = None
    # Sending this replaces the level's beams wholesale; omitting it leaves
    # them alone. Same rule as the grid's delete_missing: an absent field is
    # not an instruction to delete.
    beams: list[DeckLevelBeamBase] | None = None


class DeckLevelRead(DeckLevelBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    section_id: UUID

    calc_slab_cy: Decimal | None = None
    calc_beam_cy: Decimal | None = None
    calc_concrete_cy: Decimal | None = None
    calc_slab_rebar_lb: Decimal | None = None
    calc_beam_rebar_lb: Decimal | None = None
    calc_total_rebar_lb: Decimal | None = None
    calc_pt_sf: Decimal | None = None
    calc_pt_lb: Decimal | None = None
    calc_gb_form_ff: Decimal | None = None
    calc_beam_lf: Decimal | None = None

    calc_direct_cost: Decimal | None = None
    calc_allocated_cost: Decimal | None = None
    calc_equip_fuel: Decimal | None = None
    calc_tax: Decimal | None = None
    calc_cost: Decimal | None = None
    calc_sale: Decimal | None = None
    calc_cost_per_unit: Decimal | None = None
    calc_sale_per_unit: Decimal | None = None

    beams: list[DeckLevelBeamRead] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime


class DeckLevelBulkRow(DeckLevelBase):
    id: UUID | None = None
    beams: list[DeckLevelBeamBase] | None = None


class DeckLevelBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[DeckLevelBulkRow] = Field(default_factory=list)
    delete_missing: bool = False


class DeckTotals(BaseModel):
    section_id: UUID
    level_count: int = 0
    total_sf: Decimal = Decimal("0")
    total_perm_edge_lf: Decimal = Decimal("0")
    total_mesh_sf: Decimal = Decimal("0")
    total_slab_cy: Decimal = Decimal("0")
    total_beam_cy: Decimal = Decimal("0")
    total_concrete_cy: Decimal = Decimal("0")
    total_slab_rebar_lb: Decimal = Decimal("0")
    total_beam_rebar_lb: Decimal = Decimal("0")
    total_rebar_lb: Decimal = Decimal("0")
    total_rebar_tons: Decimal = Decimal("0")
    total_pt_sf: Decimal = Decimal("0")
    total_pt_lb: Decimal = Decimal("0")
    total_gb_form_ff: Decimal = Decimal("0")
    total_beam_lf: Decimal = Decimal("0")
    # perm edge LF + GB form FF. Every lumber line on the section rides it,
    # which is why it is a headline figure and not a detail.
    lumber_driver_lf: Decimal = Decimal("0")
    total_direct_cost: Decimal = Decimal("0")
    total_allocated_cost: Decimal = Decimal("0")
    total_equip_fuel: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_cost_per_unit: Decimal | None = None
    total_sale_per_unit: Decimal | None = None


class DeckLevelBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list[DeckLevelRead] = Field(default_factory=list)
    totals: DeckTotals | None = None
