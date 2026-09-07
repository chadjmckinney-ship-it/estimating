"""
The out-of-town day rate is the job's (sql/070, 2026-09-07).

Chad: "the out of town day rate it is per job." It was the one day rate
left at section level after sql/064 moved mobilization and the equipment
day rates up. Now: nobody can set it on a section, a new section seeds no
row for it, the card still shows it read-only, and the number on the job's
price sheet is what every section's OUT OF TOWN EXPENSE line pays.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services.price_book import ESTIMATE_LEVEL_KEYS, rate_level
from tests import piers_fixture as pif

D = Decimal
KEY = "out_of_town_day_rate"


def test_it_is_a_job_level_key():
    assert KEY in ESTIMATE_LEVEL_KEYS and rate_level(KEY) == "estimate"


def test_a_section_cannot_set_it_and_seeds_no_row_for_it(client, db, estimate):
    r = client.post(f"/api/estimates/{estimate.id}/sections", json={"kind": "piers", "name": "P", "unit": "EA"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    n = db.scalar(text("SELECT count(*) FROM section_rates WHERE section_id = :s AND key = :k"), {"s": sid, "k": KEY})
    assert n == 0, "seeding writes section-level prices only"
    r = client.put(f"/api/sections/{sid}/rates/{KEY}", json={"value": "300"})
    assert r.status_code == 400 and "whole job" in r.json()["detail"], r.text


def test_the_card_still_shows_it_read_only(client, db, estimate):
    section = pif.build(db, estimate)
    rows = {r["key"]: r for r in client.get(f"/api/sections/{section.id}/rates").json()["rows"]}
    assert KEY in rows, "shown, not hidden"
    assert rows[KEY]["level"] == "estimate" and D(rows[KEY]["value"]) == D("250")  # 01-Piers G82


def test_the_jobs_number_is_what_the_line_pays(client, db, estimate):
    section = pif.build(db, estimate)

    def line():
        lines = client.get(f"/api/sections/{section.id}/equipment").json()["lines"]
        return next(ln for ln in lines if ln["code"] == "out_of_town")

    assert D(str(line()["rate"])) == D("250")
    sheet = client.get(f"/api/estimates/{estimate.id}/prices").json()
    row = next(r for r in sheet["rows"] if r["ref_key"] == KEY and r["scope"] == "piers")
    r = client.patch(f"/api/estimates/{estimate.id}/prices/{row['id']}", json={"value": "275"})
    assert r.status_code == 200, r.text
    assert D(str(line()["rate"])) == D("275"), "the job's sheet reaches the section's line"


def test_the_seeded_rows_came_back_out(db):
    assert db.scalar(text("SELECT count(*) FROM section_rates WHERE key = :k"), {"k": KEY}) == 0
    assert db.scalar(text("SELECT count(*) FROM schema_migrations WHERE filename = '070_out_of_town_is_the_jobs.sql'")) == 1
