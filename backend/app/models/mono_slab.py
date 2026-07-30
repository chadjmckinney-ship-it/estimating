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
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
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
    drops_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    # Slab mat: #4 @ 18" o.c. each way. NULL = no mat priced on this pour.
    slab_bar_size: Mapped[int | None] = mapped_column(SmallInteger)
    slab_bar_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    # Support steel only (chairs/dowels/misc) lb/SF; NULL = system default 0.1
    support_rebar_lb_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    pt_lb_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    pt_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_slab_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_gb_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
