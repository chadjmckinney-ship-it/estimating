import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

LINE_KINDS = ("purchase", "material", "labor", "equipment", "misc", "uplift")
CATEGORIES = (
    "material", "supervision", "in_house_labor", "contract_services",
    "sub_labor", "equipment", "travel", "misc", "other",
)
CATEGORY_LABELS = {
    "material": "Material",
    "supervision": "Supervision",
    "in_house_labor": "In-house labor",
    "contract_services": "Contract services",
    "sub_labor": "Sub labor",
    "equipment": "Equipment",
    "travel": "Travel",
    "misc": "Miscellaneous",
    "other": "Other",
}


class CostCode(Base):
    """One row of the workbook's chart (sql/088): the Summary tab's breakdown."""

    __tablename__ = "cost_codes"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    # The JOB COST SUMMARY column this code feeds; NULL for a subtotal, the
    # unused code and the margin line.
    summary_column: Mapped[str | None] = mapped_column(Text)
    is_subtotal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class CostCodeLine(Base):
    """
    Where one priced line is filed (sql/088).

    `line_kind` says which line set the code is from: a purchase key the
    material-costs reader reports, a forming line, a labor line, an equipment
    line, a misc item's allowance, the fuel uplift. `inhouse_code` is the code
    a labor line takes on a section whose labor is not subcontracted.
    """

    __tablename__ = "cost_code_lines"

    line_kind: Mapped[str] = mapped_column(Text, primary_key=True)
    line_code: Mapped[str] = mapped_column(Text, primary_key=True)
    cost_code: Mapped[str] = mapped_column(Text, ForeignKey("cost_codes.code"), nullable=False)
    inhouse_code: Mapped[str | None] = mapped_column(Text, ForeignKey("cost_codes.code"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # Stamped by app/audit.py's flush hook from the signed-in person.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL"), nullable=True
    )
