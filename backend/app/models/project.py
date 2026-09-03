import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    job_number: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL")
    )

    # Notion bid list fields
    gc: Mapped[str | None] = mapped_column(Text)
    project_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_started'")
    )
    bid_due: Mapped[date | None] = mapped_column(Date)
    bid_date: Mapped[date | None] = mapped_column(Date)
    plans_url: Mapped[str | None] = mapped_column(Text)
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rev_date: Mapped[date | None] = mapped_column(Date)
    rev_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # sql/027 — ROW paving is always exempt
    tax_exempt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notion_message_id: Mapped[str | None] = mapped_column(Text)
    notion_page_id: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    estimator_links: Mapped[list["ProjectEstimator"]] = relationship(
        "ProjectEstimator",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProjectEstimator(Base):
    __tablename__ = "project_estimators"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    estimator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimators.id", ondelete="CASCADE"),
        primary_key=True,
    )
