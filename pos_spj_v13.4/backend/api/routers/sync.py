"""API central de sincronización (arquitectura híbrida, Slice 4; §8 del prompt).

`POST /api/v1/sync/events`: una estación entrega un lote de sobres y recibe un
acuse inequívoco por cada uno (ACCEPTED, DUPLICATE, CONFLICT, REJECTED, RETRY).

* Autenticación por estación: `X-SPJ-Station-Id` + `Authorization: Bearer
  <secreto>`. Sin credenciales compartidas ni de administrador; el error no dice
  si falló el id o el secreto.
* Límites: cuerpo ≤ 8 MiB, ≤ 500 sobres, y un tope de solicitudes por estación
  por minuto (429 con `Retry-After`).
* `X-Request-ID` se acepta o se genera, se devuelve y queda en el log.
* El router no decide nada de negocio: delega en el flujo de `app.state`.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.api.sync")
router = APIRouter(prefix="/v1/sync", tags=["sync"])

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_ENVELOPES = 500


class SyncWorkflow(Protocol):
    def handle(self, *, station_id: str | None, secret: str | None,
               envelopes: list) -> list[dict]: ...


class StationRateLimiter:
    """Ventana deslizante por estación, en memoria (un proceso de API)."""

    def __init__(self, per_minute: int = 60) -> None:
        self._limit = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        instante = time.monotonic() if now is None else now
        with self._lock:
            golpes = self._hits[key]
            while golpes and instante - golpes[0] > 60:
                golpes.popleft()
            if len(golpes) >= self._limit:
                return False
            golpes.append(instante)
            return True


def _bearer(request: Request) -> str | None:
    valor = request.headers.get("authorization", "")
    tipo, _, credencial = valor.partition(" ")
    return credencial.strip() if tipo.lower() == "bearer" and credencial.strip() else None


@router.post("/events")
async def push_events(request: Request, response: Response) -> dict:
    request_id = request.headers.get("x-request-id") or new_uuid()
    response.headers["X-Request-ID"] = request_id
    flujo: SyncWorkflow | None = getattr(request.app.state, "sync_workflow", None)
    if flujo is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Sincronización central no configurada")
    estacion = request.headers.get("x-spj-station-id")
    limitador: StationRateLimiter = request.app.state.sync_rate_limiter
    clave = estacion or (request.client.host if request.client else "desconocido")
    if not limitador.allow(clave):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiadas solicitudes",
                            headers={"Retry-After": "60"})
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Lote demasiado grande")
    cuerpo = await request.body()
    if len(cuerpo) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Lote demasiado grande")
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido") from None
    sobres = datos.get("envelopes") if isinstance(datos, dict) else None
    if not isinstance(sobres, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta la lista 'envelopes'")
    if len(sobres) > MAX_ENVELOPES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Máximo {MAX_ENVELOPES} sobres por solicitud")
    from backend.application.sync.central_ingestion import (
        StationAuthenticationError,
        StationNotAllowedError,
    )
    try:
        acuses = flujo.handle(station_id=estacion, secret=_bearer(request), envelopes=sobres)
    except StationAuthenticationError:
        logger.warning("sync %s: credencial inválida (estación %s)", request_id, estacion)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credencial de estación inválida",
                            headers={"WWW-Authenticate": "Bearer"}) from None
    except StationNotAllowedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from None
    logger.info("sync %s: estación %s, %s sobres", request_id, estacion, len(sobres))
    return {"request_id": request_id, "acks": acuses}
