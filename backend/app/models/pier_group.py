import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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


class PierGroup(Base):
    """
    A group of identical drilled piers (sql/037).

    One row is a GROUP, not one pier — the same shape as estimate_beam_types.
    Six groups make LBJ's 106.

    This is the first assembly that is not a pour, and the difference is not
    cosmetic: a pier has no square footage, so the SF-weighted cost allocation
    every other section uses has nothing to weigh. See costing.allocation_basis.
    """

    __tablename__ = "pier_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimate_sections.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    diameter_in: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    base_depth_ft: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, server_default=text("0")
    )
    rock_penetration_ft: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, server_default=text("0")
    )
    bell_size_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )

    vert_bars_count: Mapped[int | None] = mapped_column(SmallInteger)
    vert_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    tie_size: Mapped[int | None] = mapped_column(SmallInteger)
    tie_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    # Confinement at the top, as the drawing calls it out: a COUNT at a
    # spacing — "3 #3 stirrups at 3 inches top" — not a band length.
    band_tie_count: Mapped[int | None] = mapped_column(SmallInteger)
    band_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    dowels_count: Mapped[int | None] = mapped_column(SmallInteger)
    dowels_size: Mapped[int | None] = mapped_column(SmallInteger)
    dowels_length_ft: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    calc_total_depth_ft: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_shaft_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_bell_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_tie_count: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_vert_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_tie_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_dowel_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_drill_lf_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_drill_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    calc_direct_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_allocated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_equip_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_sale_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
