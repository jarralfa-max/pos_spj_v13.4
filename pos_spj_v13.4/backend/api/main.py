"""FastAPI application skeleton for future SPJ API entrypoints."""

from __future__ import annotations

from fastapi import FastAPI


API_TITLE = "SPJ ERP/POS API"
API_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
