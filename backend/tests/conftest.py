"""
Shared pytest fixtures: a fixture database and a rolled-back session.

The services under test call db.commit() themselves, so a plain "open a
transaction and roll it back" fixture would not hold. Instead the session is
bound to a connection whose outer transaction the test owns, with
join_transaction_mode="create_savepoint": a service commit releases a
savepoint, and the outer rollback still undoes everything at the end of the
test. Nothing a test writes survives it.

Set TEST_DATABASE_URL to point somewhere else; the name must end in `_test`.
Set REBUILD_TEST_DB=1 to force a rebuild from sql/ before the run.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import Request  # module level: `from __future__ import annotations` makes the hint a string
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.dbsetup import (  # noqa: E402
    ensure_recorded,
    is_migrated,
    rebuild,
    test_database_url,
)

# Keep app.db (imported transitively by the models) off the live database even
# though tests never use its engine.
TEST_URL = test_database_url()
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)

# A costing lookup that runs outside any price-book context RAISES here
# (sql/048). In production the same lookup falls back to the catalog and logs,
# which is what the app did before the sheet existed — but a site nobody
# threaded the book to is a job that silently reprices at today's catalog, and
# that failure has to be a red test, not a surprise in March. See
# services/price_book.py, "Why a context rather than a parameter".
os.environ["ESTIMATING_STRICT_PRICES"] = "1"
# Sign-in (sql/068): the suite signs in on every test. At production strength
# (2**15) that is ~50 ms a time, a minute over the run; the stored hash carries
# its own N, so a weaker N here verifies the same code path.
os.environ.setdefault("ESTIMATING_SCRYPT_N", "1024")

from app.models.beam_type import EstimateBeamType  # noqa: E402
from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection  # noqa: E402
from app.models.estimator import Estimator  # noqa: E402
from app.models.grade_beam import GradeBeam  # noqa: E402
from app.models.mono_slab import MonoSlab  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.calc import refresh_mono_slab_calcs  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    if os.environ.get("REBUILD_TEST_DB") == "1" or not is_migrated(TEST_URL):
        rebuild(TEST_URL)
    else:
        # An existing test database built before dbsetup recorded anything.
        # Backfill rather than skip the startup guard — the endpoint tests boot
        # the real app, and that guard is worth exercising.
        ensure_recorded(TEST_URL)
    eng = create_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """
    A session whose every write is rolled back, service commits included.

    ## `autoflush=False`, to match app/db.py — DO NOT CHANGE THIS

    This used to be left at SQLAlchemy's default of True while production ran
    False, and the divergence hid two live bugs for as long as it existed.
    Both had the same shape: a service writes a derived value through the ORM,
    then reads the same table back in **raw SQL**. Under test the read got a
    free flush and saw the new value; on the real server it saw the old one.

      * `refresh_estimate_totals` rolled a job up from pre-edit section rows,
        so the estimate total sat one edit behind on every write path.
      * `_super_days` returned stale superintendent days to the equipment
        ladder. On piers, where the days are typed rather than derived, that
        gave a zero-day ladder and priced every rental line at $0.00 — the
        section came out **$7,263.67 light** and still looked plausible.

    Both are fixed by flushing in the reader, and this session is what keeps
    them fixed: with autoflush on, neither bug is expressible here. **A harness
    more forgiving than production is a harness that certifies bugs.**
    """
    conn = engine.connect()
    outer = conn.begin()
    session = Session(
        bind=conn, join_transaction_mode="create_savepoint", autoflush=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def as_role(db):
    """
    A signed-in client for any role (sql/068): `as_role("estimator")`. The
    person is created in this test's transaction with the password
    "test-password", and the client carries the session cookie from then on.
    Every request runs inside the same rolled-back transaction as the
    fixtures, so a route that commits commits to a savepoint.
    """
    from fastapi.testclient import TestClient

    from app import auth
    from app.db import get_db
    from app.main import app

    def _db_for_tests(request: Request):
        # The audit middleware writes through this test's rolled-back session
        # rather than one of its own (sql/069, app/audit.py).
        request.state.audit_db = db
        return db

    app.dependency_overrides[get_db] = _db_for_tests
    opened = []

    def _as(role: str, *, username: str | None = None) -> TestClient:
        name = username or f"test_{role}"
        person = db.scalars(select(Estimator).where(Estimator.username == name)).first()
        if person is None:
            person = Estimator(
                username=name, full_name=f"Test {role.replace('_', ' ')}", role=role,
                password_hash=auth.hash_password("test-password"),
            )
            db.add(person)
            db.flush()
        c = TestClient(app)
        c.__enter__()
        opened.append(c)
        r = c.post("/api/auth/login", json={"username": name, "password": "test-password"})
        assert r.status_code == 200, r.text
        return c

    yield _as
    for c in opened:
        c.__exit__(None, None, None)
    app.dependency_overrides.clear()


@pytest.fixture
def client(as_role):
    """
    The app, signed in as a test admin. Copied into 33 files until 2026-09-06
    (audit P3, batch 4); one here now, and since sql/068 it signs in first.
    """
    return as_role("admin")


@pytest.fixture
def setting(db):
    """set('waste_concrete', '0.10') — writes system_settings, no recalc."""

    def _set(key: str, value: str) -> None:
        updated = db.execute(
            text("UPDATE system_settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
            {"k": key, "v": value},
        ).rowcount
        assert updated == 1, f"no such system_setting: {key}"
        db.flush()

    return _set


@pytest.fixture
def project(db) -> Project:
    row = Project(name="Test Project", location="Austin, TX")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def estimate(db, project) -> Estimate:
    row = Estimate(project_id=project.id, name="Test Estimate")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def section(db, estimate) -> EstimateSection:
    """
    The one assembly every calc test works in (sql/033).

    Markup mirrors the old estimate defaults so the hand-computed expectations
    in the calc tests did not have to move when sections arrived.
    """
    row = EstimateSection(
        estimate_id=estimate.id,
        kind="mono_slab",
        name="Mono slab on grade",
        unit="SF",
        margin_pct=Decimal("0.20"),
        contingency_pct=Decimal("0.03"),
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def make_pour(db, section):
    """
    A 10,000 SF pour: 5" slab on 2" sand, #4 mat @ 18" o.c., no PT.

    Round numbers on purpose — the expected values in the calc tests are hand
    computed from these, and every one is written out in the assertion.
    """

    def _make(**overrides) -> MonoSlab:
        fields = dict(
            section_id=section.id,
            description="Pour A",
            square_footage=Decimal("10000"),
            thickness_in=Decimal("5"),
            sand_thickness_in=Decimal("2"),
            perimeter_edge_lf=Decimal("400"),
            slab_bar_size=4,
            slab_bar_spacing_in=Decimal("18"),
            post_tension=False,
            wire_mesh=False,
        )
        fields.update(overrides)
        row = MonoSlab(**fields)
        db.add(row)
        db.flush()
        refresh_mono_slab_calcs(db, row, section)
        db.flush()
        return row

    return _make


@pytest.fixture
def pour(make_pour) -> MonoSlab:
    return make_pour()


@pytest.fixture
def make_beam(db, section):
    """
    A beam type plus one pour's usage of it.

    Default section: 12" × 24", 3-#5 top and bottom, #3 stirrups @ 18",
    200 LF on the pour.
    """

    def _make(slab: MonoSlab, **overrides) -> GradeBeam:
        length = overrides.pop("length_lf", Decimal("200"))
        fields = dict(
            section_id=section.id,
            label="GB-1",
            kind="grade_beam",
            width_in=Decimal("12"),
            height_in=Decimal("24"),
            top_bars_count=3,
            top_bars_size=5,
            bottom_bars_count=3,
            bottom_bars_size=5,
            stirrup_size=3,
            stirrup_spacing_in=Decimal("18"),
        )
        fields.update(overrides)
        beam_type = EstimateBeamType(**fields)
        db.add(beam_type)
        db.flush()

        usage = GradeBeam(
            mono_slab_id=slab.id, beam_type_id=beam_type.id, length_lf=length
        )
        db.add(usage)
        db.flush()
        refresh_mono_slab_calcs(db, slab, section)
        db.flush()
        return usage

    return _make
