"""Conflictos de replicación pendientes, resueltos EN la estación (SDLC-SYNC-002).

El central guarda un hecho en CONFLICTO y no lo proyecta. Hasta que alguien lo
resuelva, ese dinero no llega a los libros centrales, así que la estación lo
muestra en Configuración → Offline (decisión del responsable, 2026-11-05: lo
resuelve la estación, ahí).

Dos salidas, las mismas de Caja (`ResolveCashSyncConflictUseCase`), para hechos
de cualquier contexto:

- `RETRY_LOCAL`: reenvía el MISMO sobre. Si el central lo sigue teniendo en
  conflicto, responde CONFLICT y el sobre vuelve aquí: reintentar nunca lo da
  por entregado.
- `ACCEPT_REMOTE`: prevalece el central y el sobre deja de enviarse. El hecho no
  llega a los libros centrales: es una decisión explícita y queda en
  `audit_logs` con actor, motivo y operación.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.security.unwired_policy import unwired
from backend.infrastructure.db.repositories.replication.replication_repository import (
    ReplicationRepository,
)
from backend.shared.ids import validate_uuidv7

RETRY_LOCAL = "RETRY_LOCAL"
ACCEPT_REMOTE = "ACCEPT_REMOTE"
AUDIT_ACTION = "sincronizacion.conflicto.resolver"
AUDIT_ENTITY = "replication_envelope"


@dataclass(frozen=True)
class ReplicationConflictRow:
    envelope_id: str
    source: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    sequence_no: int
    error: str
    created_at: str


class ReplicationConflictQuery:
    def __init__(self, connection) -> None:
        self._repository = ReplicationRepository(connection)

    def pending(self, *, limit: int = 200) -> tuple[ReplicationConflictRow, ...]:
        return tuple(
            ReplicationConflictRow(
                envelope_id=str(fila["id"]), source=str(fila["source"]),
                event_type=str(fila["event_type"]),
                aggregate_type=str(fila["aggregate_type"]),
                aggregate_id=str(fila["aggregate_id"]),
                sequence_no=int(fila["sequence_no"]),
                error=str(fila["last_error"] or ""),
                created_at=str(fila["created_at"] or ""))
            for fila in self._repository.list_conflicts(limit=limit))


class ResolveReplicationConflictUseCase:
    def __init__(self, uow_factory: Callable[[], object], authorization=None) -> None:
        """`uow_factory()` da una unidad de trabajo con `.replication` y
        `.audit_log` (`ReplicationConflictUnitOfWork` en producción)."""
        self._uow_factory = uow_factory
        self._auth = authorization or unwired(ConfiguracionAuthorizationPolicy)

    def execute(self, *, envelope_id: str, strategy: str, reason: str, actor: str,
                operation_id: str, now: str = "") -> None:
        self._auth.require(actor, ConfiguracionPermissions.OFFLINE_GESTIONAR)
        motivo = str(reason or "").strip()
        if not motivo:
            raise ValueError("Indique el motivo de la resolución.")
        if strategy not in (RETRY_LOCAL, ACCEPT_REMOTE):
            raise ValueError("Estrategia de resolución desconocida.")
        validate_uuidv7(envelope_id)
        validate_uuidv7(operation_id)
        with self._uow_factory() as uow:
            repo = uow.replication
            sobre = repo.get(envelope_id)
            if sobre is None or sobre["state"] != "CONFLICT":
                raise LookupError("El conflicto ya no está pendiente.")
            instante = now or uow.clock_now()
            hecho = (repo.requeue(envelope_id=envelope_id, now=instante)
                     if strategy == RETRY_LOCAL
                     else repo.settle_remote(envelope_id=envelope_id, now=instante))
            if not hecho:
                raise LookupError("El conflicto ya no está pendiente.")
            estacion = repo.get_station(sobre["station_id"]) or {}
            uow.audit_log.record(
                action=AUDIT_ACTION, entity=AUDIT_ENTITY, entity_id=envelope_id,
                actor=actor, operation_id=operation_id,
                details=f"estrategia={strategy} evento={sobre['event_id']} motivo={motivo}",
                before={"state": "CONFLICT", "error": sobre["last_error"]},
                after={"state": "RETRY" if strategy == RETRY_LOCAL else "SYNCED"},
                branch_id=estacion.get("branch_id"),
            )


__all__ = [
    "ACCEPT_REMOTE", "AUDIT_ACTION", "RETRY_LOCAL", "ReplicationConflictQuery",
    "ReplicationConflictRow", "ResolveReplicationConflictUseCase",
]
