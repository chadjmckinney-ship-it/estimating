import json
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    # Rendered as text (`value #>> '{}'`) so "0.50" and true read back the same
    # way the calc helpers see them. NULL means the key EXISTS but nobody has
    # said what it is — `mobilization_ls` ships that way (sql/053). Unset is a
    # first-class state here: it is not zero, and the screen must not draw it
    # as one.
    value: str | None = None
    description: str | None = None
    updated_at: datetime | None = None

    # ------------------------------------------------------- what this IS ----
    #
    # Served rather than re-derived in JavaScript, for the same reason
    # `quote_kinds` is served on a section: a second copy of the price/rule
    # taxonomy in the front end is a copy that will disagree, and this one
    # decides whether editing a key moves an old bid.
    #
    # A PRICE is frozen on each estimate's sheet at its pull, so changing it
    # here changes what NEW work is priced at and leaves every existing job
    # alone. A RULE is read live, so changing it rewrites every open estimate
    # on the spot. Same screen, opposite consequences — see
    # claude/estimate-price-sheet-spec.md, "What is a price, and what is a
    # rule".
    is_price: bool = False
    # The registry's label and unit for a price ("Superintendent", "DAY").
    # Absent on a rule, which has no unit — a waste factor is a ratio and a
    # divisor is a count.
    label: str | None = None
    unit: str | None = None
    # Which card the screen files it under, and where that card sits. Served
    # rather than sorted in JavaScript because the ORDER is a judgement — the
    # tax rate and the day rates come before the vapor-barrier defaults — and
    # alphabetical is not it.
    group: str = "Other"
    group_order: int = 99
    # False when the value is jsonb null: EXISTS but unpriced.
    is_set: bool = True
    # What editing this rewrites, from services/recalc.settings_scope — so the
    # screen can say "this rewrites every open estimate" before the click
    # rather than after it.
    scope: dict[str, bool] = Field(default_factory=dict)
    # A key in neither MONETARY_KEYS nor RULE_KEYS. test_price_sheet_rates
    # fails the day one appears, so this should always be False; it is served
    # so the screen shows the row rather than hiding it.
    unclassified: bool = False


class SystemSettingUpdate(BaseModel):
    """
    New value. Accepts a number, a bool, or a string — settings are jsonb and
    hold all three (0.05, true, "0.50").

    **null CLEARS the key back to unset.** Not the same as zero: a company that
    has no mobilization figure is different from one that mobilizes for free,
    and sql/053 ships `mobilization_ls` in exactly that state. Without this a
    price could be set once and never taken back, which is how a guessed number
    becomes permanent.
    """

    value: Decimal | bool | str | None = Field(..., examples=[0.05, True, "0.50", None])

    def as_jsonb(self) -> str:
        """Serialise to a jsonb literal, keeping numbers numeric."""
        v = self.value
        if v is None:
            return "null"
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
