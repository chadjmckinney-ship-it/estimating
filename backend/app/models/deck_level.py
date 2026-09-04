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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.beam_type import EstimateBeamType


class DeckLevel(Base):
    """
    One level of a cast-in-place elevated deck (sql/052).

    The fifth takeoff shape, after the pour (mono_slabs), the group
    (pier_groups), the run (wall_runs) and the type (column_types) — and the
    simplest of them: an area, a thickness, two mats of bar, an edge, and the
    grade beams running through it.

    The workbook gives every level TWO rows and sums concrete and steel across
    the pair. Asked what the second row was for, Chad, 2026-09-04: "dead weight
    from the source sheet." One row per level here.
    """

    __tablename__ = "deck_levels"

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

    # The section's unit, and the basis every shared cost allocates by.
    area_sf: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    thickness_in: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, server_default=text("0")
    )
    has_cable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )
    perm_edge_lf: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )

    top_bar_size: Mapped[int | None] = mapped_column(SmallInteger)
    top_bar_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    bot_bar_size: Mapped[int | None] = mapped_column(SmallInteger)
    bot_bar_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    mesh_sf: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    # Both zero on LBJ. Asked whether stud rails were a real line or furniture
    # like the columns cure and saw cutting, Chad, 2026-09-04: "real - keep
    # it." Stud rails carry a material line AND a labor line ($500/ton).
    stud_rail_lb: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    carton_form_sf: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    calc_slab_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_beam_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_slab_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_beam_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_gb_form_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_beam_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

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
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    beams: Mapped[list["DeckLevelBeam"]] = relationship(
        back_populates="level",
        cascade="all, delete-orphan",
        order_by="DeckLevelBeam.sort_order",
        lazy="selectin",
    )


class DeckLevelBeam(Base):
    """
    How much of a beam type runs through a level.

    Same shape as GradeBeam (sql/025): the schedule lives once on
    EstimateBeamType and this is the join plus a length. The sheet has three
    fixed slots per level, and three fixed slots is exactly how it ended up
    reading CY per LF for the second one and an empty header cell for the
    third — 7 lb of steel where a 45 LF beam weighs 2,855.
    """

    __tablename__ = "deck_level_beams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    deck_level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deck_levels.id", ondelete="CASCADE"),
        nullable=False,
    )
    beam_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_beam_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    length_lf: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    calc_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_form_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    level: Mapped[DeckLevel] = relationship(back_populates="beams")
    beam_type: Mapped[EstimateBeamType] = relationship(lazy="joined")
