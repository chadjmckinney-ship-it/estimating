from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import (
    equipment,
    estimate_equipment,
    estimators,
    estimates,
    forming,
    grade_beams,
    labor,
    materials,
    mix_designs,
    mono_slabs,
    projects,
    system_settings,
)

app = FastAPI(title=settings.api_title, version=settings.api_version)

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
app.include_router(forming.router, prefix="/api")
app.include_router(labor.router, prefix="/api")
app.include_router(estimate_equipment.router, prefix="/api")
app.include_router(mono_slabs.router, prefix="/api")
app.include_router(grade_beams.router, prefix="/api")
app.include_router(mix_designs.router, prefix="/api")
app.include_router(equipment.router, prefix="/api")
app.include_router(materials.router, prefix="/api")
app.include_router(system_settings.router, prefix="/api")

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
