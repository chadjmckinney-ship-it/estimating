"""
The older forming sets read their divisors through the ladder (audit
2026-09-04, P3 — batch 1, 2026-09-06).

Columns and the deck read chairs, cure and nails through `_rate_numeric`;
the slab, paving, piers and walls sets typed the same divisors as literals —
`/ 15000.0`, `/ 300.0 / 55.0`, `/ 1500` — so a company rule for them reached
only the newer sets. Every literal is a ladder read now with the literal as
its default, which is why not one golden number moved. Two keys were new:
tie wire per roll of SF, and concrete haul-off loads per CY.
"""

from __future__ import annotations

import math

from sqlalchemy import text

from app.services.forming import load_stored_forming, refresh_and_store_forming
from tests import mono_slab_fixture as mf
from tests import paving_fixture as pf
from tests import piers_fixture as pif
from tests import walls_fixture as wf


def _line(db, sid, code):
    refresh_and_store_forming(db, sid)
    return next(ln for ln in load_stored_forming(db, sid)["lines"] if ln["code"] == code)


def _qty(db, sid, code) -> float:
    return float(_line(db, sid, code)["qty"])


def _rule(db, sid, key, value):
    db.execute(
        text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, 'test') "
             "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
        {"s": str(sid), "k": key, "v": value},
    )
    db.flush()


def test_the_slab_reads_chairs_tie_wire_cure_and_nails_from_the_ladder(db, estimate):
    s = mf.build(db, estimate)
    chairs, tie, cure, nails = (_qty(db, s.id, c) for c in ("chairs", "tie_wire", "cure", "16p"))
    assert chairs > 0 and tie > 0 and cure > 0 and nails > 0

    _rule(db, s.id, "chairs_sf_per_bag", 7500)   # half the bag's coverage -> about twice the bags
    _rule(db, s.id, "tie_wire_sf_per_roll", 7500)
    _rule(db, s.id, "cure_sf_per_gal", 150)
    _rule(db, s.id, "nails_16p_per_sf", 250)
    assert 2 * chairs - 1 <= _qty(db, s.id, "chairs") <= 2 * chairs
    assert abs(_qty(db, s.id, "tie_wire") - 2 * tie) <= 0.002  # stored to 3 dp, no ceil
    assert 2 * cure - 1 <= _qty(db, s.id, "cure") <= 2 * cure
    assert 2 * nails - 1 <= _qty(db, s.id, "16p") <= 2 * nails
    assert "7500" in _line(db, s.id, "chairs")["formula"]  # the formula names the number it used


def test_paving_reads_its_nails_and_cure_from_the_ladder(db, estimate):
    s = pf.build(db, estimate)
    sf = float(pf.TOTAL_SF)
    assert _qty(db, s.id, "cure") == 15            # the sheet's 15 drums at 350 SF/gal, unchanged
    nails = _qty(db, s.id, "16p")
    assert nails > 0

    _rule(db, s.id, "cure_sf_per_gal", 175)
    assert _qty(db, s.id, "cure") == math.ceil(sf / 175 / 55)
    _rule(db, s.id, "nails_16p_per_sf", 750)        # half the box's coverage
    assert 2 * nails - 1 <= _qty(db, s.id, "16p") <= 2 * nails


def test_piers_and_walls_read_haul_off_loads_and_cure_from_the_ladder(db, estimate):
    for build in (pif.build, wf.build):
        s = build(db, estimate)
        loads, cure = _qty(db, s.id, "haul_off"), _qty(db, s.id, "cure")
        assert loads > 0 and cure > 0
        _rule(db, s.id, "haul_off_cy_per_load", 150)  # half the load -> twice the loads
        _rule(db, s.id, "cure_sf_per_gal", 150)
        assert abs(_qty(db, s.id, "haul_off") - 2 * loads) <= 0.002  # stored to 3 dp
        assert 2 * cure - 1 <= _qty(db, s.id, "cure") <= 2 * cure
