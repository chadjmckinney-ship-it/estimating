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


class EstimateEquipmentLine(Base):
    __tablename__ = "estimate_equipment_lines"
    __table_args__ = (
        UniqueConstraint(
            "section_id", "code", name="estimate_equipment_lines_section_code_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimate_sections.id", ondelete="CASCADE"), nullable=False
    )
    group_name: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'equipment'")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    equipment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("equipment.id", ondelete="SET NULL")
    )
    days_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0")
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0")
    )
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DAY'"))
    billable_units: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0")
    )
    ext_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    formula: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # The RATE was typed (sql/058). `is_manual` pins the days and the switch;
    # only this pins the price, so a machine given days keeps following the
    # price sheet.
    rate_is_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # catalog | rate | default — where the rate came from (sql/047). "default"
    # on real days is an unpriced line wearing a plausible number.
    price_source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EstimateEquipmentSummary(Base):
    __tablename__ = "estimate_equipment_summary"

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimate_sections.id", ondelete="CASCADE"), primary_key=True
    )
    pour_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_sf: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    super_days: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0")
    )
    equip_days: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0")
    )
    total_concrete_cy: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0")
    )
    total_equipment_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    total_contract_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    cost_per_sf: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
