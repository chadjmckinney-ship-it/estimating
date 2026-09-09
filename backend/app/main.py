from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import schema_check
from app.config import settings
from app.audit import AuditMiddleware
from app.auth import current_user
from app.policy import authorize
from app.routers import (
    audit,
    auth,
    bar_sizes,
    beam_types,
    equipment,
    estimate_equipment,
    estimators,
    estimate_sections,
    estimates,
    forming,
    grade_beams,
    labor,
    materials,
    mix_designs,
    mono_slabs,
    pier_groups,
    projects,
    section_quotes,
    estimate_rules,
    section_rates,
    system_settings,
    column_types,
    deck_levels,
    estimate_prices,
    wall_runs,
    beam_runs,
    panel_types,
    misc_items,
    proposals,
    bid_requests,
    daily_reports,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Verify the schema before serving a single request.

    A missing migration used to surface as a 500 with an UndefinedColumn buried
    in a stack trace, minutes after startup, on whichever endpoint happened to
    touch the new column. It is knowable at boot, so it is checked at boot.
    """
    schema_check.check_url(settings.database_url)
    yield


app = FastAPI(
    title=settings.api_title, version=settings.api_version, lifespan=lifespan,
    # The API's own documentation is served below, behind a session (sql/083).
    docs_url=None, redoc_url=None, openapi_url=None,
)
# Every write request that reaches the API is recorded (sql/069, app/audit.py).
app.add_middleware(AuditMiddleware)

# Sign-in is the one API route that needs no session (sql/068).
app.include_router(auth.router, prefix="/api")

# Everything else: signed in, and the role is enough for the request
# (app/policy.py). Until 2026-09-07 there was no login at all and CORS was a
# wildcard with credentials allowed — any website open in a browser while the
# server ran could drive the API, and with -Lan anyone in the office could.
# The CORS middleware is gone: the SPA is served from this same origin, and
# nothing else is meant to call the API from a browser.
for _r in (
    estimators, projects, estimates, estimate_sections, forming, labor, estimate_equipment, mono_slabs, pier_groups, wall_runs, beam_runs, column_types, panel_types, misc_items, proposals, bid_requests, daily_reports, deck_levels, estimate_prices, section_quotes, section_rates, estimate_rules, grade_beams, beam_types, mix_designs, equipment, materials, system_settings, bar_sizes, audit,
):
    app.include_router(_r.router, prefix="/api", dependencies=[Depends(authorize)])

# Frontend lives at Estimate_Projects/frontend
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db": "estimating"}


# /docs, /redoc and /openapi.json for the signed-in only (sql/083). Until
# 2026-09-09 they listed every route and schema to anyone who could reach the
# port, which on the LAN was the office and through Funnel is everyone.
@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(current_user)])
def openapi_json() -> JSONResponse:
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False, dependencies=[Depends(current_user)])
def swagger_docs() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")


@app.get("/redoc", include_in_schema=False, dependencies=[Depends(current_user)])
def redoc_docs() -> HTMLResponse:
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")


if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
