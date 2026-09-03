import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MonoSlab(Base):
    __tablename__ = "mono_slabs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimate_sections.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    square_footage: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    thickness_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    post_tension: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )
    sand_thickness_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    perimeter_edge_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    wire_mesh: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Drops live in grade_beams (kind='drop') — see sql/022
    # Slab mat: #4 @ 18" o.c. each way. NULL = no mat priced on this pour.
    slab_bar_size: Mapped[int | None] = mapped_column(SmallInteger)
    slab_bar_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    # Support steel only (chairs/dowels/misc) lb/SF; NULL = system default 0.1
    support_rebar_lb_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    pt_lb_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    pt_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Paving drivers (sql/036). A paving area is a pour — same SF, thickness,
    # sand, mix and bar mat — so it lives here rather than in a table of its
    # own. These six are what it adds; a building slab leaves them NULL.
    curb_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    thick_edge_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    demo_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    slip_form: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    traffic_control: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    paving_add_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    mesh_gauge: Mapped[int | None] = mapped_column(SmallInteger)

    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_slab_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_gb_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    # Curb + thickened edge. Separate from the slab plane on purpose.
    calc_edge_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_sand_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_slab_bar_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_slab_bar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_support_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_cable_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_slab_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_gb_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_cable_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_grade_beam_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    # Poly / Stego vapor barrier SF
    calc_poly_slab_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_poly_gb_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_poly_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    # Stored cost / sale (sql/026) — rewritten by app.services.costing
    calc_sf_per_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_direct_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_allocated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # sql/027 — uplifts kept visible rather than folded into unit costs
    calc_equip_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_sale_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
