from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MonoSlabBase(BaseModel):
    section_id: UUID
    description: str | None = Field(None, examples=["Garden Style", "Bld 1 Pour 3"])
    location: str | None = None
    square_footage: Decimal = Field(..., ge=0, examples=[9525])
    thickness_in: Decimal = Field(..., gt=0, examples=[4])
    post_tension: bool = False
    mix_design_id: int | None = None
    sand_thickness_in: Decimal | None = Field(None, ge=0, examples=[2])
    perimeter_edge_lf: Decimal | None = Field(None, ge=0, examples=[500])
    wire_mesh: bool = False
    # Slab mat — plan call-out like #4 @ 18" O.C.E.W. Both required to price a mat.
    slab_bar_size: int | None = Field(
        None, ge=3, le=11, examples=[4], description="Slab mat bar size #3–#11"
    )
    slab_bar_spacing_in: Decimal | None = Field(
        None,
        gt=0,
        examples=[18],
        description="Slab mat spacing inches o.c., each way; LF = 2 × SF × 12 / spacing",
    )
    # Support steel only (chairs/dowels/misc). Blank/null → system default (0.1)
    support_rebar_lb_per_sf: Decimal | None = Field(
        None,
        ge=0,
        examples=[0.1],
        description="Override support rebar lb/SF for this pour (excludes the mat)",
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
    # --- paving drivers (sql/036) — NULL/false on a building slab ---
    curb_lf: Decimal | None = Field(
        None,
        ge=0,
        examples=[6566],
        description="Paving: LF of curb. Drives curb concrete, forming and the CURB labor line",
    )
    thick_edge_lf: Decimal | None = Field(
        None, ge=0, description="Paving: LF of thickened edge; adds LF × 1.5 × 0.18 / 27 CY"
    )
    demo_lf: Decimal | None = Field(None, ge=0, description="Paving: LF of demolition")
    slip_form: bool = False
    traffic_control: bool = False
    paving_add_per_sf: Decimal | None = Field(
        None, description="Paving: $/SF adder for this area; feeds the LABOR ADJUSTMENT line"
    )
    mesh_gauge: int | None = Field(
        None, ge=0, le=20, description="Paving: mesh gauge call-out, recorded with the takeoff"
    )
    notes: str | None = None
    sort_order: int = 0


class MonoSlabCreate(MonoSlabBase):
    # extra="forbid" (audit 2026-09-04, P2 #8): a misspelled field on a money
    # endpoint is a 422, not a silent 200. The paving grid — twenty-five areas
    # across sixteen columns, the biggest bulk save in the app — comes through
    # MonoSlabBulkRow below, and a renamed column in app.js used to be a save
    # that changed nothing and said it had.
    model_config = ConfigDict(extra="forbid")


class MonoSlabUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    location: str | None = None
    square_footage: Decimal | None = Field(None, ge=0)
    thickness_in: Decimal | None = Field(None, gt=0)
    post_tension: bool | None = None
    mix_design_id: int | None = None
    sand_thickness_in: Decimal | None = Field(None, ge=0)
    perimeter_edge_lf: Decimal | None = Field(None, ge=0)
    wire_mesh: bool | None = None
    slab_bar_size: int | None = Field(None, ge=3, le=11)
    slab_bar_spacing_in: Decimal | None = Field(None, gt=0)
    support_rebar_lb_per_sf: Decimal | None = Field(None, ge=0)
    pt_lb_per_sf: Decimal | None = Field(None, ge=0)
    pt_spacing_in: Decimal | None = Field(None, gt=0)
    curb_lf: Decimal | None = Field(None, ge=0)
    thick_edge_lf: Decimal | None = Field(None, ge=0)
    demo_lf: Decimal | None = Field(None, ge=0)
    slip_form: bool | None = None
    traffic_control: bool | None = None
    paving_add_per_sf: Decimal | None = None
    mesh_gauge: int | None = Field(None, ge=0, le=20)
    notes: str | None = None
    sort_order: int | None = None


class MonoSlabBulkRow(MonoSlabUpdate):
    """
    One row of a grid save. `id` present = update that pour, absent = create.

    Paving is entered as a table — up to twenty-five areas across sixteen
    columns — and saving it a field at a time would mean a recalc per keystroke
    on a section whose forming, labor and equipment all key off the totals.
    """

    id: UUID | None = None
    square_footage: Decimal | None = Field(None, ge=0)
    thickness_in: Decimal | None = Field(None, gt=0)


class MonoSlabBulkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    rows: list[MonoSlabBulkRow] = Field(default_factory=list, max_length=200)
    delete_missing: bool = Field(
        False,
        description=(
            "Delete pours in this section that the grid did not send back. Off "
            "by default: a save that silently drops work is worse than a row "
            "the user has to delete twice."
        ),
    )


class MonoSlabBulkResult(BaseModel):
    section_id: UUID
    created: int = 0
    updated: int = 0
    deleted: int = 0
    rows: list["MonoSlabRead"] = Field(default_factory=list)
    totals: "MonoSlabTotals | None" = None


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
    # Curb + thickened edge (paving)
    calc_edge_concrete_cy: Decimal | None = None
    calc_sand_cy: Decimal | None = None
    # Slab mat (from size + spacing); lb includes the waste_rebar lap allowance
    calc_slab_bar_lf: Decimal | None = None
    calc_slab_bar_lb: Decimal | None = None
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
    # Stored cost / sale (sql/026)
    calc_sf_per_cy: Decimal | None = None
    calc_direct_cost: Decimal | None = None
    calc_allocated_cost: Decimal | None = None
    calc_equip_fuel: Decimal | None = None
    calc_tax: Decimal | None = None
    calc_cost: Decimal | None = None
    calc_sale: Decimal | None = None
    calc_cost_per_sf: Decimal | None = None
    calc_sale_per_sf: Decimal | None = None
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

    section_id: UUID
    slab_count: int
    total_sf: Decimal
    total_concrete_cy: Decimal
    total_slab_concrete_cy: Decimal
    total_gb_concrete_cy: Decimal
    total_edge_concrete_cy: Decimal = Decimal("0")
    total_sand_cy: Decimal
    # Paving drivers; zero on a building slab
    total_curb_lf: Decimal = Decimal("0")
    total_thick_edge_lf: Decimal = Decimal("0")
    total_demo_lf: Decimal = Decimal("0")
    total_slip_form_sf: Decimal = Decimal("0")
    total_traffic_control_sf: Decimal = Decimal("0")
    total_paving_add: Decimal = Decimal("0")
    total_slab_bar_lf: Decimal = Decimal("0")
    total_slab_bar_lb: Decimal = Decimal("0")
    total_support_rebar_lb: Decimal
    total_pt_cable_lb: Decimal
    total_pt_cable_lf: Decimal
    total_grade_beam_rebar_lb: Decimal
    total_rebar_lb: Decimal
    total_poly_slab_sf: Decimal = Decimal("0")
    total_poly_gb_sf: Decimal = Decimal("0")
    total_poly_sf: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_sale: Decimal = Decimal("0")
    total_cost_per_sf: Decimal | None = None
    total_sale_per_sf: Decimal | None = None
    # What the name searches landed on — named on purpose (sql/030). These
    # were computed by section_pour_totals and DROPPED here until 2026-09-02:
    # the fourth instance of a service key that never reached the screen.
    rebar_material: str | None = None
    vapor_barrier: str | None = None
    # "section" (chosen here) / "default" (company setting) / "fallback"
    # (neither — a name search inside the vapor_barrier category)
    vapor_barrier_source: str | None = None
    vapor_tape: str | None = None
