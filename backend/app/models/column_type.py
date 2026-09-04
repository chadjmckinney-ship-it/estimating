import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ColumnType(Base):
    """
    One cast-in-place column type and how many of it there are (sql/045).

    The fourth takeoff shape, after the pour (mono_slabs), the group
    (pier_groups) and the run (wall_runs). Closest to a pier group — a quantity
    of identical things, measured in EA — but shared cost allocates by
    `calc_form_sf`, the way walls allocate by form feet, because forming is what
    a column job spends its money on.

    Three vertical bar sets, because the sheet carries three. Only the first is
    used on LBJ; the others exist so a column with different bar in its middle
    third does not have to become a second type.
    """

    __tablename__ = "column_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_sections.id", ondelete="CASCADE"),
        nullable=False,
    )

    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )

    height_ft: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("0")
    )
    length_in: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, server_default=text("0")
    )
    width_in: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, server_default=text("0")
    )
    # 4 = free-standing column, 3 = pilaster on a built wall, 2 = monolithic
    # with it (sql/051). The unformed face is always an L face, so L runs
    # along the wall. Drives calc_form_sf, which is the section's allocation
    # basis — this is the whole difference between a column and a pilaster.
    formed_faces: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("4")
    )

    vert1_count: Mapped[int | None] = mapped_column(Integer)
    vert1_size: Mapped[int | None] = mapped_column(Integer)
    vert2_count: Mapped[int | None] = mapped_column(Integer)
    vert2_size: Mapped[int | None] = mapped_column(Integer)
    vert3_count: Mapped[int | None] = mapped_column(Integer)
    vert3_size: Mapped[int | None] = mapped_column(Integer)

    tie_size: Mapped[int | None] = mapped_column(Integer)
    tie_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    dowel_count: Mapped[int | None] = mapped_column(Integer)
    dowel_size: Mapped[int | None] = mapped_column(Integer)
    dowel_length_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    calc_form_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_vert_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_tie_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_dowel_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_chamfer_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    calc_direct_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_allocated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_equip_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_sale_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
