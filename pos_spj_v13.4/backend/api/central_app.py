"""App FastAPI del SERVIDOR CENTRAL (arquitectura híbrida, Slice 4).

Distinta de `backend/api/main.py`, que es la API local de la estación (teléfono de
Logística, PWAs). El servidor central expone salud, sincronización y equipos
(vinculación por invitación, auditoría enterprise Fase 4); cada solicitud usa su
propia conexión a PostgreSQL y la cierra al terminar. Las estaciones se
autentican firmando con su llave Ed25519 (o, en transición, con el secreto del
Slice 4); el servidor nunca entrega credenciales de PostgreSQL.

En el servidor (systemd + Caddy con TLS, ADR-001):

    SPJ_PG_DSN=... uvicorn backend.api.central_app:app --host 127.0.0.1 --port 8100

TLS lo termina Caddy delante de uvicorn; uvicorn escucha sólo en localhost.
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI

from backend.api.routers.devices import router as devices_router
from backend.api.routers.sync import StationRateLimiter, router as sync_router
from backend.shared.security.device_signature import NonceCache

API_TITLE = "SPJ Servidor central"
API_VERSION = "0.1.0"


class CentralSyncWorkflow:
    """Une la ingesta con una conexión por solicitud."""

    def __init__(self, connection_factory: Callable, repository_factory: Callable,
                 projection_factory: Callable | None = None,
                 nonces: NonceCache | None = None) -> None:
        self._connect = connection_factory
        self._repository = repository_factory
        self._projection = projection_factory
        self._nonces = nonces or NonceCache()

    def handle(self, *, station_id, secret, envelopes, signed=None) -> list[dict]:
        """`signed`: `(método, ruta, encabezados, cuerpo)` cuando la solicitud viene
        firmada con la llave del equipo (Fase 4); si no, se usa el secreto."""
        from backend.application.sync.central_ingestion import CentralIngestionService

        conexion = self._connect()
        try:
            repositorio = self._repository(conexion)
            servicio = CentralIngestionService(repositorio)
            if signed is not None:
                estacion = self._signed_station(repositorio, signed)
            else:
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

    def _signed_station(self, repositorio, signed):
        from backend.application.sync.central_ingestion import (
            StationAuthenticationError,
            StationNotAllowedError,
        )
        from backend.application.sync.device_provisioning import (
            DeviceNotAuthorizedError,
            DeviceProvisioningService,
        )
        metodo, ruta, encabezados, cuerpo = signed
        try:
            return DeviceProvisioningService(repositorio, nonces=self._nonces).authenticate_signed(
                method=metodo, path=ruta, headers=encabezados, body=cuerpo)
        except DeviceNotAuthorizedError as exc:
            if exc.code == "BAD_SIGNATURE":
                raise StationAuthenticationError(str(exc)) from None
            raise StationNotAllowedError(str(exc)) from None

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


class CentralDeviceWorkflow:
    """Equipos (Fase 4): una conexión por solicitud, confirmada por el servicio y
    revertida si algo falla."""

    def __init__(self, connection_factory: Callable, repository_factory: Callable,
                 nonces: NonceCache | None = None) -> None:
        self._connect = connection_factory
        self._repository = repository_factory
        self._nonces = nonces or NonceCache()

    def _run(self, accion):
        from backend.application.sync.device_provisioning import DeviceProvisioningService

        conexion = self._connect()
        try:
            return accion(DeviceProvisioningService(self._repository(conexion),
                                                    nonces=self._nonces))
        except Exception:
            try:
                conexion.rollback()
            except Exception:
                pass
            raise
        finally:
            conexion.close()

    def enroll(self, **datos):
        return self._run(lambda servicio: servicio.enroll(**datos))

    def signed(self, *, method, path, headers, body, action, require_active=True,
               actor_user=None):
        def accion(servicio):
            estacion = servicio.authenticate_signed(method=method, path=path, headers=headers,
                                                    body=body, require_active=require_active)
            return action(servicio, estacion)
        return self._run(accion)


def create_central_app(workflow: CentralSyncWorkflow | None = None, *,
                       requests_per_minute: int = 60,
                       device_workflow: CentralDeviceWorkflow | None = None,
                       enrollments_per_minute: int = 10) -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION)
    app.state.sync_workflow = workflow
    app.state.sync_rate_limiter = StationRateLimiter(requests_per_minute)
    app.state.device_workflow = device_workflow
    app.state.enroll_rate_limiter = StationRateLimiter(enrollments_per_minute)
    app.include_router(sync_router, prefix="/api")
    app.include_router(devices_router, prefix="/api")

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
    nonces = NonceCache()
    return create_central_app(
        CentralSyncWorkflow(fabrica, PostgresCentralInboxRepository,
                            PostgresCentralProjectionRepository, nonces=nonces),
        device_workflow=CentralDeviceWorkflow(fabrica, PostgresCentralInboxRepository,
                                              nonces=nonces))


app = _from_environment()
