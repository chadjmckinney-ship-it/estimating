"""
A markup or a waste factor outside its range is refused at the API too.

test_section_bounds.py proves the database refuses one (sql/057); the audit
(2026-09-04, P3 — batch 4, 2026-09-06) noted nothing sent one through the
section PATCH, where the screen's own writes go. The schema bounds match the
CHECKs, so a value that passes here is one the database will take, and a
value the database would refuse never becomes a 500 with half a write behind
it.
"""

from __future__ import annotations

import pytest

OUT_OF_RANGE = [
    ("margin_pct", "2.5"),
    ("margin_pct", "-0.1"),
    ("contingency_pct", "3"),
    ("form_percent", "2.5"),
    ("waste_concrete", "1.5"),
]

IN_RANGE = [
    ("margin_pct", "2"),
    ("contingency_pct", "0.03"),
    ("form_percent", "2"),
    ("waste_concrete", "1"),
]


@pytest.mark.parametrize("field,value", OUT_OF_RANGE)
def test_out_of_range_is_a_422(client, section, field, value):
    r = client.patch(f"/api/sections/{section.id}", json={field: value})
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"][-1] == field


@pytest.mark.parametrize("field,value", IN_RANGE)
def test_the_edge_of_the_range_is_accepted(client, section, field, value):
    r = client.patch(f"/api/sections/{section.id}", json={field: value})
    assert r.status_code == 200, r.text
