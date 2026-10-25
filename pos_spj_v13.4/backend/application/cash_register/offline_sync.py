"""Sincronización de Caja con el servidor central — fachada de Caja sobre el
motor de replicación ÚNICO (arquitectura híbrida, Slice 2).

CASH-19 tenía su propio motor (`cash_sync_devices`/`cash_sync_envelopes`) que,
al reintentar o resolver un conflicto, escribía `cash_outbox.status`. Esa
columna es del despachador en proceso que lleva la Caja a Finanzas, que sólo
toma filas PENDING: un clic en «Sincronizar» sin servidor configurado dejaba
los movimientos en FAILED y **nunca se asentaban**. Ahora Caja usa
`ReplicationOutboxService`, que lleva su propio estado y no toca el outbox.

Esta fachada conserva lo que la pantalla de Caja ya usaba (mismas clases,
permisos `CAJA.sincronizacion.*` y alcance por sucursal). El «dispositivo» de
Caja es la estación de replicación; el ciclo envía todos los hechos de la
estación, y las vistas de Caja muestran los de Caja.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.application.sync.replication_outbox import (
    ReplicationOutboxService,
    ReplicationTransport,
)
from backend.domain.cash_register.events import CashEvents
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.infrastructure.db.repositories.replication.unit_of_work import (
    ReplicationUnitOfWork,
)
from backend.shared.ids import validate_uuidv7

#: Fuente de los hechos de Caja en el motor de replicación.
CASH_SOURCE = "cash_register"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


#: Puerto de transporte de Caja = el del motor único.
CashSyncTransport = ReplicationTransport


@dataclass(frozen=True, slots=True)
class SyncCycleResult:
    status: str
    staged: int
    sent: int
    synced: int
    retries: int
    conflicts: int


def ensure_cash_sync_device(connection, *, device_id: str | None,
                            branch_id: str | None) -> str | None:
    """Registra la terminal activa como estación de replicación si aún no lo es."""
    if not device_id or not branch_id:
        return None
    ReplicationOutboxService.register_station(connection, station_id=str(device_id),
                                              branch_id=str(branch_id))
    return str(device_id)


def _station_in_branch(uow, device_id: str, branch_id: str) -> dict:
    estacion = uow.replication.get_station(device_id)
    if estacion is None or estacion["branch_id"] != branch_id:
        raise LookupError("Sync device outside branch scope")
    return estacion


class CashOfflineSyncService:
    def __init__(self, transport: CashSyncTransport, *, batch_size: int = 50) -> None:
        self._engine = ReplicationOutboxService(transport, batch_size=batch_size)

    def synchronize(self, connection, *, device_id: str, branch_id: str,
                    now: datetime | None = None) -> SyncCycleResult:
        validate_uuidv7(device_id); validate_uuidv7(branch_id)
        with ReplicationUnitOfWork(connection) as uow:
            _station_in_branch(uow, device_id, branch_id)
        r = self._engine.synchronize(connection, station_id=device_id, now=now)
        return SyncCycleResult(r.status, r.staged, r.sent, r.synced, r.retries, r.conflicts)


def _cash_row(fila: dict) -> dict:
    """Forma que ya mostraba la pantalla de Caja."""
    return {"id": fila["id"], "sequence_no": fila["sequence_no"],
            "aggregate_version": fila["aggregate_version"], "state": fila["state"],
            "attempt_count": fila["attempt_count"], "next_attempt_at": fila["next_attempt_at"],
            "remote_revision": fila["remote_revision"], "conflict_json": fila["conflict_json"],
            "created_at": fila["created_at"], "synced_at": fila["synced_at"],
            "event_name": fila["event_type"], "operation_id": fila["operation_id"],
            "entity_id": fila["aggregate_id"], "last_error": fila["last_error"]}


class CashSyncStateQueryService:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def _require(self, actor_user_id: str, branch_id: str) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_VIEW,
                                    branch_id=branch_id)

    def get(self, connection, *, device_id: str, branch_id: str,
            actor_user_id: str) -> dict:
        self._require(actor_user_id, branch_id)
        with ReplicationUnitOfWork(connection) as uow:
            estacion = _station_in_branch(uow, device_id, branch_id)
            conteo = uow.replication.counts(device_id, source=CASH_SOURCE)
        return {**estacion,
                "pending_count": conteo["PENDING"] + conteo["RETRY"] + conteo["IN_FLIGHT"],
                "conflict_count": conteo["CONFLICT"], "dead_count": conteo["DEAD"],
                "synced_count": conteo["SYNCED"]}

    def list_envelopes(self, connection, *, device_id: str, branch_id: str,
                       actor_user_id: str, limit: int = 100) -> list[dict]:
        self._require(actor_user_id, branch_id)
        with ReplicationUnitOfWork(connection) as uow:
            _station_in_branch(uow, device_id, branch_id)
            return [_cash_row(f) for f in uow.replication.list_recent(
                device_id, source=CASH_SOURCE, limit=limit)]

    def list_conflicts(self, connection, *, device_id: str, branch_id: str,
                       actor_user_id: str) -> list[dict]:
        """Conflictos y envíos MUERTOS de Caja: los dos requieren una decisión."""
        self._require(actor_user_id, branch_id)
        with ReplicationUnitOfWork(connection) as uow:
            _station_in_branch(uow, device_id, branch_id)
            filas = uow.replication.list_recent(device_id, source=CASH_SOURCE,
                                                states=("CONFLICT", "DEAD"), limit=500)
        return [_cash_row(f) for f in sorted(filas, key=lambda f: f["sequence_no"])]


class RegisterCashSyncDeviceUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, device_id: str, branch_id: str,
                actor_user_id: str, online: bool = True) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_MANAGE,
                                    branch_id=branch_id)
        ReplicationOutboxService.register_station(connection, station_id=device_id,
                                                  branch_id=branch_id, online=online)


class SetCashSyncConnectivityUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, device_id: str, branch_id: str,
                actor_user_id: str, online: bool) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_MANAGE,
                                    branch_id=branch_id)
        with ReplicationUnitOfWork(connection) as uow:
            _station_in_branch(uow, device_id, branch_id)
            uow.replication.set_connectivity(station_id=device_id, online=online,
                                             now=_iso(_now()))


class ResolveCashSyncConflictUseCase:
    """`RETRY_LOCAL`: reenvía el MISMO hecho, idéntico, para que el servidor lo
    reevalúe una vez corregido su lado (también sirve para un envío MUERTO).
    CASH-19 le subía la versión, pero la versión es parte de la huella: el
    servidor habría visto el mismo event_id con otro contenido. `ACCEPT_REMOTE`: prevalece el
    servidor y el sobre deja de enviarse. Las dos exigen motivo y dejan rastro
    (`CASH_SYNC_CONFLICT_RESOLVED`): ninguna corrección es silenciosa."""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, envelope_id: str, strategy: str,
                reason: str, branch_id: str, actor_user_id: str,
                operation_id: str) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_MANAGE,
                                    branch_id=branch_id)
        if not reason.strip():
            raise ValueError("Conflict resolution requires a reason")
        if strategy not in ("RETRY_LOCAL", "ACCEPT_REMOTE"):
            raise ValueError("Unknown conflict strategy")
        for value in (envelope_id, branch_id, actor_user_id, operation_id):
            validate_uuidv7(value)
        timestamp = _iso(_now())
        with CashRegisterUnitOfWork(connection) as cash:
            with ReplicationUnitOfWork(connection) as uow:
                sobre = uow.replication.get(envelope_id)
                if sobre is None or sobre["source"] != CASH_SOURCE:
                    raise LookupError("Sync conflict not found")
                _station_in_branch(uow, sobre["station_id"], branch_id)
                hecho = (uow.replication.requeue(envelope_id=envelope_id, now=timestamp)
                         if strategy == "RETRY_LOCAL"
                         else uow.replication.settle_remote(envelope_id=envelope_id,
                                                            now=timestamp))
                if not hecho:
                    raise RuntimeError("Conflict is no longer pending")
            _record(cash, CashEvents.SYNC_CONFLICT_RESOLVED,
                    operation_id=operation_id, entity_id=envelope_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    reason=reason, strategy=strategy,
                    remote_revision=sobre["remote_revision"])
