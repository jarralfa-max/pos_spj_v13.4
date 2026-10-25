"""Motor de replicación ÚNICO de la estación hacia el servidor central
(arquitectura híbrida, Slice 2; ADR-004).

Reemplaza a los motores parciales (CASH-19 en Caja, INV-22 en Inventario, el
envío fuera de línea de Mermas). Un ciclo:

1. **Preparar**: cada hecho nuevo de los outbox de contexto recibe su sobre
   (`ReplicationEnvelope`), con la secuencia siguiente de la estación y la
   versión siguiente de su agregado. Un hecho que no cumple el contrato queda
   MUERTO con el motivo, visible; nunca se descarta en silencio.
2. **Recuperar**: lo que quedó EN VUELO por un cierre o una caída vuelve a
   reintento (entrega «al menos una vez»; el servidor deduplica por event_id).
3. **Enviar** un lote en orden de secuencia, fuera de la transacción local:
   la red nunca retiene un bloqueo de la base.
4. **Aplicar acuses**: SYNCED (aceptado o duplicado con la misma huella),
   CONFLICT (queda a resolver y bloquea SÓLO a su agregado), DEAD (rechazo
   permanente o demasiados intentos), RETRY (espera exponencial con jitter).

Nunca cambia el `status` de los outbox de origen: ésos son de su despachador en
proceso. El motor viejo de Caja lo hacía y sacaba movimientos del camino a
Finanzas (ver migración 350).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence

from backend.infrastructure.db.repositories.replication.unit_of_work import (
    ReplicationUnitOfWork,
)
from backend.infrastructure.sync.replication_sources import DEFAULT_SOURCES, ReplicationSource
from backend.shared.ids import derived_uuidv7, validate_uuidv7
from backend.shared.sync.replication_envelope import (
    EnvelopeError,
    ReplicationAck,
    ReplicationEnvelope,
    ReplicationOutcome,
    envelope_from_outbox_event,
)

logger = logging.getLogger("spj.sync.replication")

#: Tras tantos intentos fallidos un sobre pasa a MUERTO (visible, reencolable).
MAX_ATTEMPTS = 25
#: Un sobre EN VUELO más viejo que esto se considera interrumpido.
LEASE = timedelta(minutes=5)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RetryPolicy:
    """Espera exponencial con *full jitter*: aleatoria entre 0 y el tope del
    intento, para que cinco sucursales que vuelven a la vez no golpeen al
    servidor al mismo segundo."""

    base_seconds: float = 2.0
    cap_seconds: float = 15 * 60

    def delay(self, attempt: int, rng: random.Random) -> timedelta:
        tope = min(self.cap_seconds, self.base_seconds * (2 ** max(0, min(attempt, 20))))
        return timedelta(seconds=max(1.0, rng.uniform(0, tope)))


class ReplicationTransport(Protocol):
    def push(self, *, station_id: str, branch_id: str,
             envelopes: Sequence[ReplicationEnvelope]) -> Sequence[ReplicationAck]: ...


class TransportUnavailable(Exception):
    """El transporte no pudo entregar el lote (red, servidor caído)."""


class MissingReplicationTransport:
    """Mientras no haya servidor central configurado: todo queda en cola local."""

    def push(self, *, station_id, branch_id, envelopes):
        raise TransportUnavailable("Servidor central de sincronización no configurado")


@dataclass(frozen=True)
class ReplicationCycleResult:
    status: str
    staged: int
    recovered: int
    sent: int
    synced: int
    retries: int
    conflicts: int
    dead: int


class ReplicationOutboxService:
    def __init__(self, transport: ReplicationTransport, *,
                 sources: Sequence[ReplicationSource] = DEFAULT_SOURCES,
                 batch_size: int = 50, retry: RetryPolicy = RetryPolicy(),
                 rng: random.Random | None = None) -> None:
        if not 1 <= batch_size <= 500:
            raise ValueError("El lote de sincronización va de 1 a 500")
        self._transport = transport
        self._sources = tuple(sources)
        self._batch_size = batch_size
        self._retry = retry
        self._rng = rng or random.Random()

    # ── estación ────────────────────────────────────────────────────────
    @staticmethod
    def register_station(connection, *, station_id: str, branch_id: str,
                         online: bool = True, now: datetime | None = None) -> None:
        validate_uuidv7(station_id)
        validate_uuidv7(branch_id)
        with ReplicationUnitOfWork(connection) as uow:
            uow.replication.register_station(
                station_id=station_id, branch_id=branch_id, online=online,
                now=_iso(now or datetime.now(timezone.utc)))

    # ── preparar ────────────────────────────────────────────────────────
    def stage(self, connection, *, station_id: str, now: datetime | None = None) -> int:
        instante = _iso(now or datetime.now(timezone.utc))
        preparados = 0
        with ReplicationUnitOfWork(connection) as uow:
            estacion = uow.replication.get_station(station_id)
            if estacion is None:
                raise LookupError("Estación de sincronización no registrada")
            for fuente in self._sources:
                if not fuente.exists(connection):
                    continue
                restante = self._batch_size * 4 - preparados
                if restante <= 0:
                    break
                for fila in fuente.pending_rows(connection, limit=restante):
                    self._stage_row(uow, fuente, fila, estacion, instante)
                    preparados += 1
        if preparados:
            logger.info("replicación: %s hechos preparados en la estación %s",
                        preparados, station_id)
        return preparados

    def _stage_row(self, uow, fuente, fila, estacion, instante) -> None:
        repo = uow.replication
        evento, agregado = fuente.normalize(fila, station_branch_id=estacion["branch_id"])
        secuencia = repo.next_sequence(estacion["id"])
        version = repo.next_aggregate_version(agregado, str(evento["entity_id"]))
        try:
            sobre = envelope_from_outbox_event(
                evento, aggregate_type=agregado, aggregate_version=version,
                workstation_id=estacion["id"], sequence_no=secuencia)
            if repo.has_event(sobre.event_id):
                # El mismo hecho llegó por dos outbox: se envía una vez; el segundo
                # queda visible en vez de romper la preparación en cada ciclo.
                raise EnvelopeError("DUPLICATE_EVENT_ID_ACROSS_SOURCES",
                                    f"event_id {sobre.event_id} ya tiene sobre")
        except EnvelopeError as exc:
            # Un hecho que no cumple el contrato no se pierde: queda MUERTO y visible.
            logger.warning("replicación: %s/%s no cumple el contrato (%s): %s",
                           fuente.name, fila.get("id"), exc.code, exc)
            repo.add(station_id=estacion["id"], source=fuente.name,
                     source_row_id=str(fila["id"]),
                     event_id=derived_uuidv7(f"{fuente.name}:{fila['id']}", "replication-dead"),
                     event_type=str(evento.get("event_name") or "UNKNOWN"),
                     operation_id=str(evento.get("operation_id")), sequence_no=secuencia,
                     aggregate_type=agregado, aggregate_id=str(evento.get("entity_id")),
                     aggregate_version=version,
                     envelope_json=_json_safe({"invalid_event": evento}), content_hash="",
                     now=instante, state="DEAD", last_error=f"{exc.code}: {exc}")
            return
        repo.add(station_id=estacion["id"], source=fuente.name, source_row_id=str(fila["id"]),
                 event_id=sobre.event_id, event_type=sobre.event_type,
                 operation_id=sobre.operation_id, sequence_no=secuencia,
                 aggregate_type=agregado, aggregate_id=sobre.aggregate_id,
                 aggregate_version=version, envelope_json=sobre.to_json(),
                 content_hash=sobre.content_hash, now=instante)

    # ── ciclo completo ──────────────────────────────────────────────────
    def synchronize(self, connection, *, station_id: str,
                    now: datetime | None = None) -> ReplicationCycleResult:
        momento = now or datetime.now(timezone.utc)
        instante = _iso(momento)
        preparados = self.stage(connection, station_id=station_id, now=momento)
        with ReplicationUnitOfWork(connection) as uow:
            estacion = uow.replication.get_station(station_id)
            recuperados = uow.replication.recover_stale(
                station_id=station_id, claimed_before=_iso(momento - LEASE), now=instante)
            if estacion["connectivity"] == "OFFLINE":
                conteo = uow.replication.counts(station_id)
                return ReplicationCycleResult("OFFLINE", preparados, recuperados, 0, 0, 0,
                                              conteo["CONFLICT"], conteo["DEAD"])
            tomados = uow.replication.claim_ready(station_id=station_id, now=instante,
                                                  limit=self._batch_size)
            if not tomados:
                conteo = uow.replication.counts(station_id)
                final = "CONFLICT" if conteo["CONFLICT"] else "IDLE"
                uow.replication.finish_cycle(station_id=station_id, status=final, now=instante)
                return ReplicationCycleResult(final, preparados, recuperados, 0, 0, 0,
                                              conteo["CONFLICT"], conteo["DEAD"])
        sobres = [ReplicationEnvelope.from_json(fila["envelope_json"]) for fila in tomados]
        acuses: dict[str, ReplicationAck] = {}
        error_transporte = ""
        try:
            for acuse in self._transport.push(station_id=station_id,
                                              branch_id=estacion["branch_id"],
                                              envelopes=sobres):
                acuses[acuse.event_id] = acuse
        except Exception as exc:   # la red nunca tumba al POS: todo vuelve a la cola
            error_transporte = f"TRANSPORT_UNAVAILABLE: {exc}"[:500]
            logger.info("replicación: transporte no disponible (%s)", exc)
        return self._apply(connection, station_id, tomados, acuses, error_transporte,
                           momento, preparados, recuperados)

    def _apply(self, connection, station_id, tomados, acuses, error_transporte, momento,
               preparados, recuperados) -> ReplicationCycleResult:
        instante = _iso(momento)
        sincronizados = reintentos = conflictos = muertos = 0
        with ReplicationUnitOfWork(connection) as uow:
            repo = uow.replication
            for fila in tomados:
                acuse = acuses.get(fila["event_id"])
                if acuse is not None and acuse.outcome.settles:
                    repo.mark_synced(envelope_id=fila["id"],
                                     remote_revision=acuse.remote_revision, now=instante)
                    sincronizados += 1
                elif acuse is not None and acuse.outcome is ReplicationOutcome.CONFLICT:
                    repo.mark_conflict(envelope_id=fila["id"],
                                       remote_revision=acuse.remote_revision,
                                       error=acuse.error_code, conflict=acuse.conflict)
                    conflictos += 1
                elif acuse is not None and acuse.outcome is ReplicationOutcome.REJECTED:
                    repo.mark_dead(envelope_id=fila["id"],
                                   error=f"{acuse.error_code}: {acuse.message}")
                    muertos += 1
                else:
                    motivo = (f"{acuse.error_code}: {acuse.message}" if acuse is not None
                              else error_transporte or "NO_ACK")
                    if fila["attempt_count"] >= MAX_ATTEMPTS:
                        repo.mark_dead(envelope_id=fila["id"], error=f"MAX_ATTEMPTS: {motivo}")
                        muertos += 1
                    else:
                        espera = self._retry.delay(fila["attempt_count"], self._rng)
                        repo.mark_retry(envelope_id=fila["id"],
                                        next_attempt_at=_iso(momento + espera), error=motivo)
                        reintentos += 1
            conteo = repo.counts(station_id)
            final = ("CONFLICT" if conteo["CONFLICT"] else
                     "RETRYING" if reintentos else "IDLE")
            repo.finish_cycle(station_id=station_id, status=final, now=instante,
                              error=error_transporte or None)
        logger.info("replicación %s: enviados=%s sincronizados=%s reintentos=%s "
                    "conflictos=%s muertos=%s", station_id, len(tomados), sincronizados,
                    reintentos, conflictos, muertos)
        return ReplicationCycleResult(final, preparados, recuperados, len(tomados),
                                      sincronizados, reintentos, conflictos,
                                      conteo["DEAD"])

    # ── consultas y resolución ──────────────────────────────────────────
    @staticmethod
    def status(connection, *, station_id: str, source: str | None = None) -> dict:
        with ReplicationUnitOfWork(connection) as uow:
            estacion = uow.replication.get_station(station_id)
            if estacion is None:
                raise LookupError("Estación de sincronización no registrada")
            return {**estacion, "counts": uow.replication.counts(station_id, source=source)}


def _json_safe(valor) -> str:
    import json
    return json.dumps(valor, ensure_ascii=False, default=str, sort_keys=True)


__all__ = [
    "LEASE", "MAX_ATTEMPTS", "MissingReplicationTransport", "ReplicationCycleResult",
    "ReplicationOutboxService", "ReplicationTransport", "RetryPolicy", "TransportUnavailable",
]
