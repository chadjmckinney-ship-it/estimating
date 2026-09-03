from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MixDesign(Base):
    """
    The master list of mix prices.

    `unit_cost` IS the price — one per mix, kept current as supplier numbers come
    in. Chad, 2026-09-02: "a master list of rough mix prices that we get from
    suppliers that we update as we get them, then as we start an estimate, it
    pulls those numbers." A per-supplier dated history (`mix_prices`) was built
    alongside this in sql/005, never populated, and dropped in sql/047.
    """

    __tablename__ = "mix_designs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    strength_psi: Mapped[int | None] = mapped_column(Integer)
    has_ash: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_air: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sack_count: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    typical_use: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'CY'"))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ConcreteSupplier(Base):
    __tablename__ = "concrete_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
