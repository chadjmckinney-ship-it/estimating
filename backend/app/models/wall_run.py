import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WallRun(Base):
    """
    One wall type and the footing under it (sql/040).

    The pairing is the workbook's and it is right: you do not take off a
    retaining wall without the footing, the two share a length, and the
    footing's width drives the excavation the wall sits in.

    Measured in FORM FEET — see calc_form_ff, which is contact area on one
    face.
    """

    __tablename__ = "wall_runs"

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

    # Drives sand, excavation, backfill and the french drain. An interior wall
    # gets none of them, which is why it is per row rather than per section.
    backfill: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )

    length_ft: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, server_default=text("0"))
    wall_thick_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default=text("0"))
    wall_height_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default=text("0"))

    horiz_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    horiz_size: Mapped[int | None] = mapped_column(Integer)
    horiz_mats: Mapped[int | None] = mapped_column(Integer)
    vert_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    vert_size: Mapped[int | None] = mapped_column(Integer)
    vert_mats: Mapped[int | None] = mapped_column(Integer)

    ftg_width_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default=text("0"))
    ftg_thick_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default=text("0"))
    ftg_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    ftg_size: Mapped[int | None] = mapped_column(Integer)
    ftg_mats: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    calc_form_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_footing_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_wall_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_footing_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_horiz_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_vert_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_footing_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_lap_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_sand_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_excavate_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_backfill_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_drain_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    # The wall/footing split (sql/042). calc_wall_cost + calc_footing_cost =
    # calc_cost exactly: the footing half is computed and the wall takes the
    # remainder, so they cannot drift apart from the row.
    calc_wall_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_wall_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_wall_cost_per_ff: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_wall_sale_per_ff: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_footing_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_footing_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_footing_cost_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_footing_sale_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

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
