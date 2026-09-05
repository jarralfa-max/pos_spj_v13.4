"""FastAPI application skeleton for future SPJ API entrypoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.routers.analytics import router as analytics_router
from backend.api.routers.driver_logistics import router as driver_logistics_router
from backend.api.routers.mobile_logistics import router as mobile_logistics_router


API_TITLE = "SPJ ERP/POS API"
API_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION)
    app.include_router(mobile_logistics_router, prefix="/api")
    app.include_router(driver_logistics_router, prefix="/api")
    app.include_router(analytics_router, prefix="/api")

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    pwa = Path(__file__).resolve().parents[2] / "frontend" / "web" / "logistics"
    if pwa.is_dir():
        app.mount("/mobile/logistics", StaticFiles(directory=pwa, html=True),
                  name="mobile-logistics-pwa")

    driver_pwa = Path(__file__).resolve().parents[2] / "frontend" / "web" / "delivery"
    if driver_pwa.is_dir():
        app.mount("/mobile/delivery", StaticFiles(directory=driver_pwa, html=True),
                  name="driver-pwa")
    return app


app = create_app()
