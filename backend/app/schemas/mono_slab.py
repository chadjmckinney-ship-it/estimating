from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MonoSlabBase(BaseModel):
    estimate_id: UUID
    description: str | None = Field(None, examples=["Garden Style", "Bld 1 Pour 3"])
    location: str | None = None
    square_footage: Decimal = Field(..., ge=0, examples=[9525])
    thickness_in: Decimal = Field(..., gt=0, examples=[4])
    post_tension: bool = False
    mix_design_id: int | None = None
    sand_thickness_in: Decimal | None = Field(None, ge=0, examples=[2])
    perimeter_edge_lf: Decimal | None = Field(None, ge=0, examples=[500])
    wire_mesh: bool = False
    drops_ff: Decimal | None = Field(None, ge=0)
    # SOG rates (lb/SF). Blank/null → system default (usually 1.0)
    support_rebar_lb_per_sf: Decimal | None = Field(
        None, ge=0, examples=[1.0], description="Override support rebar lb/SF for this pour"
    )
    pt_lb_per_sf: Decimal | None = Field(
        None, ge=0, examples=[1.0], description="Optional PT weight lb/SF (legacy / supplier weight)"
    )
    pt_spacing_in: Decimal | None = Field(
        None,
        gt=0,
        examples=[48],
        description="SOG PT cable spacing inches o.c.; slab LF = SF × 12 / spacing",
    )
    notes: str | None = None
    sort_order: int = 0


class MonoSlabCreate(MonoSlabBase):
    pass


class MonoSlabUpdate(BaseModel):
    description: str | None = None
    location: str | None = None
    square_footage: Decimal | None = Field(None, ge=0)
    thickness_in: Decimal | None = Field(None, gt=0)
    post_tension: bool | None = None
    mix_design_id: int | None = None
    sand_thickness_in: Decimal | None = Field(None, ge=0)
    perimeter_edge_lf: Decimal | None = Field(None, ge=0)
    wire_mesh: bool | None = None
    drops_ff: Decimal | None = Field(None, ge=0)
    support_rebar_lb_per_sf: Decimal | None = Field(None, ge=0)
    pt_lb_per_sf: Decimal | None = Field(None, ge=0)
    pt_spacing_in: Decimal | None = Field(None, gt=0)
    notes: str | None = None
    sort_order: int | None = None


class BeamKindTotals(BaseModel):
    """One pour role: grade_beam | exposed | drop (all add CY/rebar/poly to the pour)."""

    count: int = 0
    length_lf: Decimal = Decimal("0")
    rebar_lb: Decimal = Decimal("0")
    concrete_cy: Decimal = Decimal("0")
    poly_sf: Decimal = Decimal("0")


class MonoSlabRead(MonoSlabBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    calc_concrete_cy: Decimal | None = None
    calc_slab_concrete_cy: Decimal | None = None
    # Sum of grade_beam + exposed + drop concrete (name kept for compatibility)
    calc_gb_concrete_cy: Decimal | None = None
    calc_sand_cy: Decimal | None = None
    calc_support_rebar_lb: Decimal | None = None
    calc_pt_cable_lb: Decimal | None = None
    calc_pt_slab_lf: Decimal | None = None
    calc_pt_gb_lf: Decimal | None = None
    calc_pt_cable_lf: Decimal | None = None
    # Sum of grade_beam + exposed + drop rebar
    calc_grade_beam_rebar_lb: Decimal | None = None
    calc_total_rebar_lb: Decimal | None = None
    # Poly / Stego vapor barrier SF
    calc_poly_slab_sf: Decimal | None = None  # pour plane SF
    calc_poly_gb_sf: Decimal | None = None  # beam wrap sum
    calc_poly_sf: Decimal | None = None  # (slab + beams) × (1 + waste_poly)
    # Per-kind material totals (forming/labor for Exp/Drops is separate, later)
    beam_breakdown: dict[str, BeamKindTotals] | None = None
    # Effective rates used in last calc (pour override or system default)
    effective_support_rebar_lb_per_sf: Decimal | None = None
    effective_pt_lb_per_sf: Decimal | None = None
    mix_design_name: str | None = None
    mix_design_code: str | None = None
    created_at: datetime
    updated_at: datetime


class MonoSlabTotals(BaseModel):
    """Rollup of calc fields for an estimate."""

    estimate_id: UUID
    slab_count: int
    total_sf: Decimal
    total_concrete_cy: Decimal
    total_slab_concrete_cy: Decimal
    total_gb_concrete_cy: Decimal
    total_sand_cy: Decimal
    total_support_rebar_lb: Decimal
    total_pt_cable_lb: Decimal
    total_pt_cable_lf: Decimal
    total_grade_beam_rebar_lb: Decimal
    total_rebar_lb: Decimal
    total_poly_slab_sf: Decimal = Decimal("0")
    total_poly_gb_sf: Decimal = Decimal("0")
    total_poly_sf: Decimal = Decimal("0")
