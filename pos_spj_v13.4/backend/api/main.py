"""FastAPI application skeleton for future SPJ API entrypoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routers.analytics import router as analytics_router
from backend.domain.logistics.exceptions import LogisticsDomainError
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

    # Una regla de negocio rechazada es un 400 con su motivo (antes salía como
    # «Internal Server Error» y el teléfono no decía por qué).
    @app.exception_handler(ValueError)
    @app.exception_handler(LookupError)
    @app.exception_handler(LogisticsDomainError)
    async def _business_rule(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    async def _forbidden(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    def _root() -> RedirectResponse:
        """Desde el teléfono basta teclear la dirección del equipo."""
        return RedirectResponse("/mobile/logistics/")

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
