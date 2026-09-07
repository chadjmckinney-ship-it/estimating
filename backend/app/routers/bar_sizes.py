"""
The bar catalog, for the grids' pick-lists.

    GET /api/bar-sizes  ->  [{"size": 3, "weight_lb_per_ft": 0.376}, ...]

Read straight from `bar_weights`, the same table every steel formula weighs
bar from, so the list a grid offers is exactly the list the database accepts.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["bar-sizes"])


class BarSizeRead(BaseModel):
    size: int
    weight_lb_per_ft: Decimal


@router.get("/bar-sizes", response_model=list[BarSizeRead])
def list_bar_sizes(db: Session = Depends(get_db)) -> list[BarSizeRead]:
    rows = db.execute(
        text("SELECT bar_size, weight_lb_per_ft FROM bar_weights ORDER BY bar_size")
    ).all()
    return [BarSizeRead(size=int(r[0]), weight_lb_per_ft=Decimal(str(r[1]))) for r in rows]
