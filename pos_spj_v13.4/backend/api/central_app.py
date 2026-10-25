"""App FastAPI del SERVIDOR CENTRAL (arquitectura híbrida, Slice 4).

Distinta de `backend/api/main.py`, que es la API local de la estación (teléfono de
Logística, PWAs). El servidor central sólo expone salud y sincronización; cada
solicitud usa su propia conexión a PostgreSQL y la cierra al terminar.

En el servidor (systemd + Caddy con TLS, ADR-001):

    SPJ_PG_DSN=... uvicorn backend.api.central_app:app --host 127.0.0.1 --port 8100

TLS lo termina Caddy delante de uvicorn; uvicorn escucha sólo en localhost.
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI

from backend.api.routers.sync import StationRateLimiter, router as sync_router

API_TITLE = "SPJ Servidor central"
API_VERSION = "0.1.0"


class CentralSyncWorkflow:
    """Une la ingesta con una conexión por solicitud."""

    def __init__(self, connection_factory: Callable, repository_factory: Callable,
                 projection_factory: Callable | None = None) -> None:
        self._connect = connection_factory
        self._repository = repository_factory
        self._projection = projection_factory

    def handle(self, *, station_id, secret, envelopes) -> list[dict]:
        from backend.application.sync.central_ingestion import CentralIngestionService

        conexion = self._connect()
        try:
            servicio = CentralIngestionService(self._repository(conexion))
            estacion = servicio.authenticate(station_id, secret)
            acuses = [acuse.to_dict() for acuse in servicio.ingest(estacion, envelopes).acks]
            self._project(conexion)
            return acuses
        except Exception:
            try:
                conexion.rollback()
            except Exception:
                pass
            raise
        finally:
            conexion.close()

    def _project(self, conexion) -> None:
        """Proyecta lo recién aceptado (Slice 5). Mejor esfuerzo: los hechos ya
        están confirmados; si la proyección falla se reintenta en la siguiente
        solicitud o con `scripts/central_stations.py project`."""
        if self._projection is None:
            return
        from backend.application.sync.central_projection import CentralProjector

        try:
            CentralProjector(self._projection(conexion)).run_once()
        except Exception:
            import logging
            logging.getLogger("spj.sync.projection").exception("proyección diferida")
            try:
                conexion.rollback()
            except Exception:
                pass


def create_central_app(workflow: CentralSyncWorkflow | None = None, *,
                       requests_per_minute: int = 60) -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION)
    app.state.sync_workflow = workflow
    app.state.sync_rate_limiter = StationRateLimiter(requests_per_minute)
    app.include_router(sync_router, prefix="/api")

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok" if app.state.sync_workflow is not None else "unconfigured"}

    return app


def _from_environment() -> FastAPI:
    """La app que arranca uvicorn: PostgreSQL desde `SPJ_PG_DSN`. Sin la variable
    la app arranca, responde 503 en `/sync` y `/health` dice `unconfigured`."""
    from backend.infrastructure.db.database import POSTGRES_DSN_ENV

    if not os.environ.get(POSTGRES_DSN_ENV):
        return create_central_app(None)
    from backend.infrastructure.central.projection_repository import (
        PostgresCentralProjectionRepository,
    )
    from backend.infrastructure.central.sync_inbox_repository import (
        PostgresCentralInboxRepository,
    )
    from backend.infrastructure.db.database import DatabaseSettings, create_connection_factory

    fabrica = create_connection_factory(DatabaseSettings.postgresql_from_env())
    return create_central_app(CentralSyncWorkflow(fabrica, PostgresCentralInboxRepository,
                                                  PostgresCentralProjectionRepository))


app = _from_environment()
