"""
The bar sizes the app knows — one list, used by every schema that carries one.

`bar_weights` (sql/001, extended by sql/066) is the catalog: #3 through #11,
and since 2026-09-06 #14 and #18 as well. A size that is not in it weighs
nothing in every steel formula, silently — a #14 column vertical priced at
zero pounds and nothing said so (audit 2026-09-04, P3). So the database
refuses one (every bar-size column is a foreign key to the catalog), the
schemas refuse one by name before it gets that far, and the grids offer a
pick-list instead of a number box.

This tuple mirrors the table on purpose: the schemas cannot query, and a bar
size is not something that changes without a migration. `tests/test_bar_sizes.py`
fails the day the two disagree.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator

BAR_SIZES: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 18)


def check_bar_size(v: int) -> int:
    if v not in BAR_SIZES:
        sizes = ", ".join(f"#{s}" for s in BAR_SIZES)
        raise ValueError(f"bar size #{v} is not in the catalog — sizes are {sizes}")
    return v


BarSize = Annotated[int, AfterValidator(check_bar_size)]
