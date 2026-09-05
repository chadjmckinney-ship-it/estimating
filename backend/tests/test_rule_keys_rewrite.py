"""
Every rule rewrites something, or is named as the exception.

`recalc.settings_scope` maps a changed company setting to the takeoffs it
invalidates, and the settings PATCH sweeps exactly that scope — or, when the
scope is empty, saves and reports "This key feeds no stored calculation, so
nothing needed rewriting."

That sentence was true for `mobilization_ls` the morning after sql/053
seeded it, and false the moment the line existed (test_company_settings has
the regression guard). On 2026-09-04 the full check found 39 of the 56 rule
keys in the same position — every `pier_*`, `lumber_*`, `nails_*`,
`reshoring_*`, `columns_per_super_week` — mapped to nothing by an allow-list
that named the keys it knew. None of the 39 was seeded in `system_settings`
yet, which is the only reason the sentence had not been printed over a real
change. The next seeded rule would have printed it.

The rule now: a RULE key the lists do not name rewrites everything, because
"everything" is what the Recalculate button does and "nothing" is a company
change that reaches nothing. `NO_RECALC_KEYS` names the two that genuinely
feed no stored figure (the quote band, read when a card is drawn). An UNKNOWN
key — one on neither list — still rewrites nothing, as before.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services import price_book as pb
from app.services import recalc
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.recalc import settings_scope

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ------------------------------------------------------------- the registry


def test_every_rule_key_rewrites_something_or_is_named_as_a_no_op():
    silent = sorted(
        k for k in pb.RULE_KEYS
        if k not in recalc.NO_RECALC_KEYS and not any(settings_scope([k]).values())
    )
    assert silent == [], (
        f"rule keys whose company edit would report 'nothing needed rewriting': {silent}"
    )


def test_the_no_op_list_is_short_and_made_of_rules():
    """
    Two keys, both the quote band. A key added here is a decision that a
    company change to it can never move a stored number — say why in
    recalc.py, beside the list.
    """
    assert recalc.NO_RECALC_KEYS == frozenset({"quote_warn_low_ratio", "quote_warn_high_ratio"})
    assert recalc.NO_RECALC_KEYS <= pb.RULE_KEYS
    for key in recalc.NO_RECALC_KEYS:
        assert not any(settings_scope([key]).values()), key


def test_the_lists_that_name_a_narrower_reach_still_win():
    """The catch-all is the last elif, not the first: a mapped key keeps its map."""
    assert settings_scope(["form_percent"]) == {
        "pours": False, "forming": True, "labor": False, "equipment": False,
    }
    assert settings_scope(["labor_super_sf_per_week"]) == {
        "pours": False, "forming": False, "labor": True, "equipment": True,
    }
    # ...and a rule nobody mapped gets the whole sweep.
    assert all(settings_scope(["nails_16p_per_sf"]).values())
    assert all(settings_scope(["pier_cover_in"]).values())


def test_an_unknown_key_still_rewrites_nothing():
    """Not on either list means not classified, and not classified means no sweep."""
    assert not any(settings_scope(["some_future_key"]).values())


# ------------------------------------------------------------ end to end ----


def test_a_rule_the_lists_never_named_reaches_the_stored_takeoff(client, db, estimate):
    """
    The bug, through the screen's own endpoint.

    `form_rental_percent` is the share of a paving section's curb that rents
    its forms — a rule, read through the ladder by the paving equipment set
    (FORM RENTAL: curb LF × form rental % × $/contact ft). No assembly row
    carries it and the code default is 0, so the company figure is the one in
    charge — and it is on none of the lists `settings_scope` used to consult.
    Seed it, set it through PATCH, and the stored line has to move. Before
    this the PATCH returned 200, said "nothing needed rewriting", and the
    line sat at zero feet.

    (The key had to be found by asking the rates card what a paving section
    actually READS — most divisors are hard-coded in the older line sets or
    answered by an assembly row, which is its own note.)
    """
    from tests import paving_fixture as pf

    section = pf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()

    def line():
        return {ln["code"]: ln for ln in load_stored_equipment(db, section.id)["lines"]}["form_rental"]

    assert D(str(line()["days_qty"])) == 0, "nobody rents forms until somebody says so"

    db.execute(
        text(
            "INSERT INTO system_settings (key, value) "
            "VALUES ('form_rental_percent', to_jsonb(CAST('0' AS text))) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value"
        )
    )
    db.commit()

    r = client.patch("/api/system-settings/form_rental_percent", json={"value": "0.5"})
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["scope"]["equipment"] is True
    assert report["recalculated"], "a rule change has to rewrite something"
    assert "nothing needed rewriting" not in (report["note"] or "")

    db.expire_all()
    after = line()
    assert D(str(after["days_qty"])) == (pf.TOTAL_CURB_LF * D("0.5")).quantize(D("0.0001")), (
        "curb LF × 50% — the company rule reached the stored line"
    )
    assert D(str(after["ext_cost"])) > 0
