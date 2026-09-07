from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import schema_check
from app.config import settings
from app.routers import (
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
    title=settings.api_title, version=settings.api_version, lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(estimators.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(estimates.router, prefix="/api")
app.include_router(estimate_sections.router, prefix="/api")
app.include_router(forming.router, prefix="/api")
app.include_router(labor.router, prefix="/api")
app.include_router(estimate_equipment.router, prefix="/api")
app.include_router(mono_slabs.router, prefix="/api")
app.include_router(pier_groups.router, prefix="/api")
app.include_router(wall_runs.router, prefix="/api")
app.include_router(column_types.router, prefix="/api")
app.include_router(deck_levels.router, prefix="/api")
app.include_router(estimate_prices.router, prefix="/api")
app.include_router(section_quotes.router)
app.include_router(section_rates.router, prefix="/api")
app.include_router(estimate_rules.router, prefix="/api")
app.include_router(grade_beams.router, prefix="/api")
app.include_router(beam_types.router, prefix="/api")
app.include_router(mix_designs.router, prefix="/api")
app.include_router(equipment.router, prefix="/api")
app.include_router(materials.router, prefix="/api")
app.include_router(system_settings.router, prefix="/api")
app.include_router(bar_sizes.router, prefix="/api")

# Frontend lives at Estimate_Projects/frontend
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db": "estimating"}


if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
