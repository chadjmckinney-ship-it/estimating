from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MixDesign(Base):
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

    prices: Mapped[list["MixPrice"]] = relationship(
        "MixPrice", back_populates="mix_design", lazy="selectin"
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

    prices: Mapped[list["MixPrice"]] = relationship(
        "MixPrice", back_populates="supplier", lazy="selectin"
    )


class MixPrice(Base):
    __tablename__ = "mix_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mix_design_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concrete_suppliers.id", ondelete="CASCADE"), nullable=False
    )
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    price_as_of: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    mix_design: Mapped[MixDesign] = relationship("MixDesign", back_populates="prices")
    supplier: Mapped[ConcreteSupplier] = relationship("ConcreteSupplier", back_populates="prices")
