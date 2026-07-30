import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EstimateLaborLine(Base):
    __tablename__ = "estimate_labor_lines"
    __table_args__ = (
        UniqueConstraint("estimate_id", "code", name="estimate_labor_lines_estimate_id_code_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
    )
    group_name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, server_default=text("0"))
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default=text("0"))
    ext_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    formula: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EstimateLaborSummary(Base):
    __tablename__ = "estimate_labor_summary"

    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), primary_key=True
    )
    pour_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_sf: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, server_default=text("0"))
    drops_ff: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, server_default=text("0"))
    total_rebar_lb: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    total_rebar_tons: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0")
    )
    super_weeks: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0")
    )
    super_days: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0")
    )
    total_labor_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    total_supervision_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    cost_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
