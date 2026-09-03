import json
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    # Rendered as text (`value #>> '{}'`) so "0.50" and true read back the same
    # way the calc helpers see them.
    value: str | None = None
    description: str | None = None
    updated_at: datetime | None = None


class SystemSettingUpdate(BaseModel):
    """
    New value. Accepts a number, a bool, or a string — settings are jsonb and
    hold all three (0.05, true, "0.50").
    """

    value: Decimal | bool | str = Field(..., examples=[0.05, True, "0.50"])

    def as_jsonb(self) -> str:
        """Serialise to a jsonb literal, keeping numbers numeric."""
        v = self.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, Decimal):
            # No normalize(): it would rewrite 0.70 as 0.7 and 0.10 as 0.1,
            # churning the stored text for no numeric gain. "f" keeps it out of
            # exponent notation.
            return format(v, "f")
        s = str(v).strip()
        # A numeric-looking string stays numeric so `value #>> '{}'` parses.
        try:
            Decimal(s)
        except Exception:
            return json.dumps(s)
        return s


class EstimateRecalcResult(BaseModel):
    estimate_id: str
    name: str
    pours: int = 0
    forming: bool = False
    labor: bool = False
    equipment: bool = False


class SkippedEstimate(BaseModel):
    estimate_id: str
    name: str
    status: str | None = None


class RecalcReport(BaseModel):
    changed_keys: list[str] = Field(default_factory=list)
    scope: dict[str, bool] = Field(
        default_factory=dict, description="Which derivations were invalidated"
    )
    recalculated: list[EstimateRecalcResult] = Field(default_factory=list)
    skipped: list[SkippedEstimate] = Field(
        default_factory=list,
        description="Frozen estimates (final / archived) left at their bid numbers",
    )
    note: str | None = None
