import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class StampedBy:
    """
    `updated_by`: who last changed an INPUT on this row (sql/069).

    Set by app/audit.py's flush hook from the signed-in person, for a new
    row and for an edit that touched something other than a calc_* column.
    A recalc rewriting the calc_* columns does not restamp the row.
    """

    @declared_attr
    def updated_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL"), nullable=True
        )
