"""
Every bar size comes from the catalog (audit 2026-09-04, P3 — batch 1, 2026-09-06).

A #14 column vertical weighed nothing: bar_weights stopped at #11, the grids
took any number, the schemas allowed 0-20, and bar_lb_per_ft returned zero
for a size it could not find. Now the catalog carries #14 and #18 (sql/066),
every bar-size column is a foreign key to it, every schema refuses a size
that is not in it by name, and the grids offer the catalog as a pick-list.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.bar_sizes import BAR_SIZES
from app.db import get_db
from app.main import app
from app.services.walls import bar_lb_per_ft
from tests import columns_fixture as cf

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _column(client, section, **fields):
    row = {"label": "C9", "qty": 2, "height_ft": 10, "length_in": 24, "width_in": 24,
           "vert1_count": 8, "vert1_size": 8, **fields}
    return client.put("/api/column-types/bulk", json={"section_id": str(section.id), "rows": [row]})


def test_the_catalog_and_the_registry_agree(client, db):
    sizes = [r["size"] for r in client.get("/api/bar-sizes").json()]
    assert tuple(sizes) == BAR_SIZES
    assert 14 in sizes and 18 in sizes


def test_a_14_and_an_18_weigh_something_now(db):
    assert bar_lb_per_ft(db, 14) == D("7.65")
    assert bar_lb_per_ft(db, 18) == D("13.6")
    assert bar_lb_per_ft(db, 5) == D("1.043")  # and nothing else moved


def test_a_size_the_catalog_lacks_is_refused_by_name(client, db, estimate):
    section = cf.build(db, estimate)
    r = _column(client, section, vert1_size=12)
    assert r.status_code == 422, r.text
    err = r.json()["detail"][0]
    assert err["loc"][-1] == "vert1_size" and "not in the catalog" in err["msg"], err


def test_a_14_column_vertical_prices_its_steel(client, db, estimate):
    section = cf.build(db, estimate)
    r = _column(client, section, vert1_size=14)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["label"] == "C9")
    assert row["vert1_size"] == 14
    # 2 columns x 8 bars x 10 ft x 7.65 lb/ft, before waste and the rest of the cage
    assert D(row["calc_total_rebar_lb"]) >= D("1224")


def test_the_database_refuses_a_size_the_catalog_lacks(db, estimate):
    section = cf.build(db, estimate)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text("UPDATE column_types SET vert1_size = 2 WHERE section_id = :s"),
                {"s": str(section.id)},
            )
