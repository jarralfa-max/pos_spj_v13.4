"""Ingesta central: el servidor recibe los sobres de una estación (arquitectura
híbrida, Slice 4; §6.3 del prompt maestro).

Por cada sobre, dentro de SU transacción anidada (un sobre que falla no tumba el
lote), en este orden:

1. **Contrato**: versión del sobre, tipos, huella (`ReplicationEnvelope.from_dict`).
   Inválido → REJECTED (permanente, a revisión en la estación).
2. **Alcance**: el sobre lo firmó la estación autenticada (`workstation_id`) y es
   de SU sucursal. Una estación comprometida no escribe en otra sucursal ni se
   hace pasar por otra estación → REJECTED.
3. **Idempotencia**: el mismo `event_id` con la misma huella → DUPLICATE (la
   estación lo da por entregado); con otra huella → CONFLICT `EVENT_ID_REUSED`.
   Nunca se sobrescribe.
4. **Secuencia**: el mismo `sequence_no` de la estación ya usado por otro hecho →
   CONFLICT `SEQUENCE_REUSED` (p. ej. una base de estación restaurada de un
   respaldo viejo que vuelve a numerar).
5. **Orden por agregado**: la misma estación manda una versión ≤ a la última que
   ya escribió de ese agregado → se guarda como CONFLICT
   `AGGREGATE_VERSION_REGRESSION`, con su registro en `sync_conflicts`.
6. Si todo pasa → se registra como APPLIED en el libro central de hechos y se
   avanza la cabeza del agregado. Las proyecciones por contexto (ventas,
   inventario…) consumen ese libro en los Slices 5–9.

Un error de almacenamiento revierte sólo ese sobre y responde RETRY.

**Autorización del actor**: hoy el límite es la estación autenticada, activa y
acotada a su sucursal. Validar el permiso del usuario (`actor_id`) contra el
catálogo central exige que los usuarios y permisos estén replicados (Slice 7,
datos maestros): el puerto `ActorAuthorizer` ya existe para conectarlo, y por
omisión acepta (el sobre ya fue autorizado localmente por la estación).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from backend.application.sync.station_credentials import verify_station_secret
from backend.shared.ids import is_uuidv7
from backend.shared.sync.replication_envelope import (
    EnvelopeError,
    ReplicationAck,
    ReplicationEnvelope,
    ReplicationOutcome,
)

logger = logging.getLogger("spj.sync.central")

#: Tope de sobres por solicitud (igual al máximo del motor de la estación).
MAX_BATCH = 500


class StationAuthenticationError(Exception):
    """Credencial ausente o inválida (no se dice cuál de las dos)."""


class StationNotAllowedError(Exception):
    """La estación existe pero está suspendida o dada de baja."""


class CentralInboxRepository(Protocol):
    """Puerto del libro central de hechos (PostgreSQL en producción)."""

    def get_station(self, station_id: str) -> Mapping[str, Any] | None: ...
    def savepoint(self): ...
    def fact_hash(self, event_id: str) -> str | None: ...
    def event_for_sequence(self, station_id: str, sequence_no: int) -> str | None: ...
    def insert_fact(self, envelope: ReplicationEnvelope, *, station_id: str, status: str,
                    error_code: str | None, now: datetime) -> bool: ...
    def station_head(self, aggregate_type: str, aggregate_id: str,
                     station_id: str) -> int | None: ...
    def advance_head(self, envelope: ReplicationEnvelope, *, station_id: str,
                     now: datetime) -> None: ...
    def add_conflict(self, *, event_id: str, kind: str, details: Mapping[str, Any],
                     now: datetime) -> None: ...
    def touch_station(self, station_id: str, *, now: datetime) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class ActorAuthorizer(Protocol):
    def allows(self, envelope: ReplicationEnvelope, station: Mapping[str, Any]) -> bool: ...


class StationScopedAuthorizer:
    """Mientras el catálogo central no esté replicado (Slice 7): el sobre ya lo
    autorizó la estación al ejecutar el caso de uso; aquí rige el alcance de la
    estación (verificado aparte)."""

    def allows(self, envelope, station) -> bool:
        return True


@dataclass(frozen=True)
class IngestionResult:
    acks: tuple[ReplicationAck, ...]

    def count(self, outcome: ReplicationOutcome) -> int:
        return sum(1 for a in self.acks if a.outcome is outcome)


class CentralIngestionService:
    def __init__(self, repository: CentralInboxRepository, *,
                 authorizer: ActorAuthorizer | None = None) -> None:
        self._repo = repository
        self._authorizer = authorizer or StationScopedAuthorizer()

    # ── autenticación ───────────────────────────────────────────────────
    def authenticate(self, station_id: str | None, secret: str | None) -> Mapping[str, Any]:
        if not station_id or not is_uuidv7(station_id):
            raise StationAuthenticationError("Credencial de estación inválida")
        estacion = self._repo.get_station(station_id)
        if estacion is None or not verify_station_secret(secret, estacion["credential_hash"]):
            raise StationAuthenticationError("Credencial de estación inválida")
        if estacion["status"] != "ACTIVE":
            raise StationNotAllowedError(f"La estación está {estacion['status']}")
        return estacion

    # ── ingesta ─────────────────────────────────────────────────────────
    def ingest(self, station: Mapping[str, Any], envelopes: Sequence[Mapping[str, Any]],
               *, now: datetime | None = None) -> IngestionResult:
        if len(envelopes) > MAX_BATCH:
            raise ValueError(f"Máximo {MAX_BATCH} sobres por solicitud")
        instante = now or datetime.now(timezone.utc)
        acuses = [self._one(station, crudo, instante) for crudo in envelopes]
        self._repo.touch_station(str(station["id"]), now=instante)
        self._repo.commit()
        resultado = IngestionResult(tuple(acuses))
        logger.info("ingesta %s: aceptados=%s duplicados=%s conflictos=%s rechazados=%s "
                    "reintentos=%s", station["id"],
                    *(resultado.count(o) for o in (
                        ReplicationOutcome.ACCEPTED, ReplicationOutcome.DUPLICATE,
                        ReplicationOutcome.CONFLICT, ReplicationOutcome.REJECTED,
                        ReplicationOutcome.RETRY)))
        return resultado

    def _one(self, station, crudo, instante) -> ReplicationAck:
        event_id = str((crudo or {}).get("event_id") or "") if isinstance(crudo, Mapping) else ""
        try:
            sobre = ReplicationEnvelope.from_dict(crudo)
        except EnvelopeError as exc:
            return self._ack(event_id, "REJECTED", exc.code, str(exc))
        estacion_id = str(station["id"])
        if sobre.workstation_id != estacion_id:
            return self._ack(sobre.event_id, "REJECTED", "STATION_MISMATCH",
                             "El sobre es de otra estación")
        if sobre.branch_id != str(station["branch_id"]):
            return self._ack(sobre.event_id, "REJECTED", "BRANCH_SCOPE",
                             "La estación no puede escribir en otra sucursal")
        if not self._authorizer.allows(sobre, station):
            return self._ack(sobre.event_id, "REJECTED", "ACTOR_NOT_AUTHORIZED",
                             "El usuario no tiene permiso para esta operación")
        try:
            with self._repo.savepoint():
                return self._record(sobre, estacion_id, instante)
        except Exception as exc:   # sólo este sobre se revierte; la estación reintenta
            logger.exception("ingesta: no se pudo registrar %s", sobre.event_id)
            return self._ack(sobre.event_id, "RETRY", "STORAGE_ERROR", str(exc)[:200])

    def _record(self, sobre: ReplicationEnvelope, estacion_id: str, instante) -> ReplicationAck:
        repo = self._repo
        huella = repo.fact_hash(sobre.event_id)
        if huella is not None:
            return self._already_known(sobre, huella, estacion_id, instante)
        otro = repo.event_for_sequence(estacion_id, sobre.sequence_no)
        if otro is not None:
            return self._ack(sobre.event_id, "CONFLICT", "SEQUENCE_REUSED",
                             f"La secuencia {sobre.sequence_no} ya es del hecho {otro}",
                             conflict={"event_id": otro})
        ultima = repo.station_head(sobre.aggregate_type, sobre.aggregate_id, estacion_id)
        if ultima is not None and sobre.aggregate_version <= ultima:
            repo.insert_fact(sobre, station_id=estacion_id, status="CONFLICT",
                             error_code="AGGREGATE_VERSION_REGRESSION", now=instante)
            repo.add_conflict(event_id=sobre.event_id, kind="AGGREGATE_VERSION_REGRESSION",
                              details={"incoming_version": sobre.aggregate_version,
                                       "last_version": ultima}, now=instante)
            return self._ack(sobre.event_id, "CONFLICT", "AGGREGATE_VERSION_REGRESSION",
                             f"Versión {sobre.aggregate_version} ≤ {ultima} ya aplicada",
                             conflict={"last_version": ultima})
        if not repo.insert_fact(sobre, station_id=estacion_id, status="APPLIED",
                                error_code=None, now=instante):
            # Otra entrega concurrente del mismo hecho ganó la inserción (la base lo
            # garantiza con la PK): se responde según la huella que quedó.
            return self._already_known(sobre, repo.fact_hash(sobre.event_id), estacion_id,
                                       instante)
        repo.advance_head(sobre, station_id=estacion_id, now=instante)
        return self._ack(sobre.event_id, "ACCEPTED")

    def _already_known(self, sobre, huella, estacion_id, instante) -> ReplicationAck:
        if huella == sobre.content_hash:
            return self._ack(sobre.event_id, "DUPLICATE")
        self._repo.add_conflict(event_id=sobre.event_id, kind="EVENT_ID_REUSED",
                                details={"stored_hash": huella,
                                         "incoming_hash": sobre.content_hash,
                                         "station_id": estacion_id}, now=instante)
        return self._ack(sobre.event_id, "CONFLICT", "EVENT_ID_REUSED",
                         "El mismo event_id llegó con otro contenido",
                         conflict={"stored_hash": huella})

    @staticmethod
    def _ack(event_id: str, outcome: str, error_code: str = "", message: str = "",
             conflict: Mapping[str, Any] | None = None) -> ReplicationAck:
        if not is_uuidv7(event_id):
            # Sin event_id legible no hay a quién responder por id: se usa uno
            # derivado para que el acuse sea válido y la estación lo registre.
            from backend.shared.ids import derived_uuidv7
            event_id = derived_uuidv7(str(event_id or "sin-id"), "rejected-envelope")
        return ReplicationAck(event_id=event_id, outcome=outcome, error_code=error_code,
                              message=message, remote_revision="", conflict=conflict)


__all__ = [
    "ActorAuthorizer", "CentralInboxRepository", "CentralIngestionService", "IngestionResult",
    "MAX_BATCH", "StationAuthenticationError", "StationNotAllowedError",
    "StationScopedAuthorizer",
]
