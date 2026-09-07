"""
The recalc report says what moved (audit 2026-09-04, P3 — batch 4, 2026-09-06).

`RecalcReport.recalculated` was typed as estimate-level pours/forming/labor/
equipment flags that `recalc_estimate` never emits — it reports per section —
so the response model dropped everything but the estimate's name, and the
settings toast could only count estimates. The shape now follows the service:
each estimate carries its sections, each section its flags and its money.
"""

from __future__ import annotations

from tests import walls_fixture as wf

SECTION_KEYS = {"section_id", "name", "kind", "pours", "forming", "labor", "equipment", "cost", "sale"}


def test_a_setting_save_reports_each_section_it_rewrote(client, db, estimate):
    s = wf.build(db, estimate)
    r = client.patch("/api/system-settings/waste_concrete", json={"value": "0.07"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["scope"]["pours"] is True
    mine = next(e for e in rep["recalculated"] if e["estimate_id"] == str(estimate.id))
    assert "pours" not in mine, "the estimate-level flags never existed; the sections carry them"
    assert mine["cost"] is not None and mine["sale"] is not None
    sec = next(x for x in mine["sections"] if x["section_id"] == str(s.id))
    assert SECTION_KEYS <= set(sec), sorted(sec)
    assert sec["kind"] == "walls_footings" and sec["pours"] >= 1
    assert sec["cost"] is not None


def test_recalc_all_reports_the_same_shape(client, db, estimate):
    wf.build(db, estimate)
    r = client.post("/api/system-settings/recalc-all")
    assert r.status_code == 200, r.text
    mine = next(e for e in r.json()["recalculated"] if e["estimate_id"] == str(estimate.id))
    assert mine["sections"] and SECTION_KEYS <= set(mine["sections"][0])
