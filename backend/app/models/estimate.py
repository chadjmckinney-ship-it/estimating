import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Estimate(Base):
    __tablename__ = "estimates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    estimator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    notes: Mapped[str | None] = mapped_column(Text)
    # Wastes, form%, vapor barrier and tape describe an assembly, so they live on
    # estimate_sections (sql/033-034), not here.
    #
    # Markup stays, but its meaning narrowed: these are the DEFAULTS a new
    # section is created with. The markup a section is priced at is its own.
    margin_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0.20")
    )
    contingency_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0.03")
    )
    calc_total_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_total_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_total_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_sale_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
