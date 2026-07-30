import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.beam_type import EstimateBeamType


class GradeBeam(Base):
    """
    How much of a beam type a pour uses.

    Before sql/025 this row carried the whole section and bar schedule, re-keyed
    for every pour. That now lives once on EstimateBeamType; this is the join
    plus a length.

    The section fields are still readable here as proxies to the type, so the
    calc service can work from a single object.
    """

    __tablename__ = "grade_beams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    mono_slab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mono_slabs.id", ondelete="CASCADE"), nullable=False
    )
    beam_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_beam_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    length_lf: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    calc_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_cable_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    # Poly wrap SF (Excel): (2 × H″ / 12) × L ft — sides only; bottom in pour SF
    calc_poly_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    beam_type: Mapped[EstimateBeamType] = relationship(
        back_populates="usages", lazy="joined"
    )


def _proxy(name: str) -> property:
    """Read the section field from the type, so callers see one flat object."""

    def getter(self: GradeBeam):
        t = self.beam_type
        return getattr(t, name) if t is not None else None

    getter.__name__ = name
    return property(getter)


# The calc service reads these off the beam; they belong to the type now.
for _field in (
    "kind",
    "label",
    "width_in",
    "height_in",
    "top_bars_count",
    "top_bars_size",
    "bottom_bars_count",
    "bottom_bars_size",
    "mid_bars_count",
    "mid_bars_size",
    "stirrup_size",
    "stirrup_spacing_in",
    "l_bars_count",
    "l_bars_size",
    "l_bars_spacing_in",
    "pt_cables_count",
):
    setattr(GradeBeam, _field, _proxy(_field))
del _field
