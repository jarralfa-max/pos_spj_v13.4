"""Sobre de replicación: el contrato versionado con que una estación entrega un
hecho de negocio al servidor central (arquitectura híbrida, Slice 1; §6.1 del
prompt maestro; ADR-004).

Lo que viaja es un hecho YA confirmado en la base local (sale del outbox del
contexto en la misma transacción que lo produjo). El servidor lo vuelve a
autenticar y autorizar con el catálogo central: nada de este sobre otorga
permisos por sí mismo; `authorization` es sólo una referencia verificable.

Reglas del contrato:

* **Identidad.** `event_id` es la clave de idempotencia del transporte: el
  servidor aplica cada `event_id` una sola vez. `operation_id` es la del caso de
  uso (un reintento del mismo negocio). Todo identificador es UUIDv7 canónico.
* **Huella.** `content_hash` = SHA-256 de la forma canónica de lo que el hecho
  ES (tipo, agregado, versión, payload…), no de cómo viajó (secuencia, hora de
  envío). Si llega el mismo `event_id` con otra huella, es un CONFLICTO
  (`EVENT_ID_REUSED`), nunca una sobrescritura silenciosa.
* **Orden.** `sequence_no` crece de 1 en 1 por estación; `aggregate_version`
  ordena los cambios de un mismo agregado. El servidor detecta huecos y
  versiones fuera de orden con ellos.
* **Dinero y cantidades.** `Decimal` viaja como texto exacto (`"100.50"`
  conserva la escala). Un `float` en cualquier parte del payload es un ERROR:
  no se serializa y no se acepta.
* **Fechas.** Instantes con zona horaria, normalizados a UTC.
* **Versiones.** `envelope_version` es la forma del sobre; `schema_version`, la
  del payload de ese tipo de evento. Un sobre de versión desconocida se
  rechaza con `ENVELOPE_VERSION_UNSUPPORTED` (no se intenta adivinar).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from backend.shared.ids import is_uuidv7

#: Forma vigente del sobre. Subirla exige agregar el lector de la anterior.
ENVELOPE_VERSION = 1
SUPPORTED_ENVELOPE_VERSIONS = frozenset({1})
#: Tope del payload serializado (protege al servidor y a la cola local).
MAX_PAYLOAD_BYTES = 256 * 1024

_EVENT_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
_AGGREGATE_TYPE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class EnvelopeError(ValueError):
    """El sobre no cumple el contrato. `code` es estable para el servidor."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ── forma canónica ──────────────────────────────────────────────────────────
def _canonical(value: Any, path: str = "payload") -> Any:
    """Valores JSON deterministas. Rechaza lo que perdería exactitud."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, float):
        raise EnvelopeError("FLOAT_NOT_ALLOWED",
                            f"{path} es float; dinero y cantidades viajan como Decimal")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise EnvelopeError("DECIMAL_NOT_FINITE", f"{path} no es un Decimal finito")
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise EnvelopeError("NAIVE_DATETIME", f"{path} no tiene zona horaria")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _canonical(value.value, path)
    if isinstance(value, Mapping):
        salida = {}
        for clave, contenido in value.items():
            if not isinstance(clave, str):
                raise EnvelopeError("NON_STRING_KEY", f"{path} tiene una clave no textual")
            salida[clave] = _canonical(contenido, f"{path}.{clave}")
        return salida
    if isinstance(value, (list, tuple)):
        return [_canonical(v, f"{path}[{i}]") for i, v in enumerate(value)]
    raise EnvelopeError("UNSERIALIZABLE", f"{path} es {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """JSON determinista: claves ordenadas, sin espacios, UTF-8 sin escapar."""
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _require_uuid(nombre: str, valor: Any, *, optional: bool = False) -> None:
    if valor in (None, "") and optional:
        return
    if not is_uuidv7(valor):
        raise EnvelopeError("INVALID_IDENTIFIER", f"{nombre} no es un UUIDv7 canónico: {valor!r}")


def _utc(nombre: str, valor: datetime) -> datetime:
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        raise EnvelopeError("NAIVE_DATETIME", f"{nombre} debe ser un instante con zona horaria")
    return valor.astimezone(timezone.utc)


# ── sobre ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReplicationEnvelope:
    event_id: str
    operation_id: str
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    branch_id: str
    workstation_id: str
    sequence_no: int
    occurred_at: datetime
    payload: Mapping[str, Any]
    actor_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    #: Referencia verificable (p. ej. `{"permission": "...", "authorizer_user_id": "..."}`).
    #: El servidor la vuelve a validar; nunca concede nada por sí sola.
    authorization: Mapping[str, Any] = field(default_factory=dict)
    envelope_version: int = ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if self.envelope_version not in SUPPORTED_ENVELOPE_VERSIONS:
            raise EnvelopeError("ENVELOPE_VERSION_UNSUPPORTED",
                                f"Versión de sobre {self.envelope_version} no soportada")
        for nombre in ("event_id", "operation_id", "aggregate_id", "branch_id",
                       "workstation_id"):
            _require_uuid(nombre, getattr(self, nombre))
        for nombre in ("actor_id", "correlation_id", "causation_id"):
            _require_uuid(nombre, getattr(self, nombre), optional=True)
        if self.event_id == self.operation_id:
            raise EnvelopeError("IDENTITY_COLLISION",
                                "event_id y operation_id deben ser distintos")
        if not _EVENT_TYPE.match(str(self.event_type)):
            raise EnvelopeError("INVALID_EVENT_TYPE", f"Tipo de evento inválido: {self.event_type!r}")
        if not _AGGREGATE_TYPE.match(str(self.aggregate_type)):
            raise EnvelopeError("INVALID_AGGREGATE_TYPE",
                                "aggregate_type va como <contexto>.<agregado>, "
                                f"recibido {self.aggregate_type!r}")
        for nombre, minimo in (("schema_version", 1), ("aggregate_version", 0),
                               ("sequence_no", 1)):
            valor = getattr(self, nombre)
            if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
                raise EnvelopeError("INVALID_ORDINAL", f"{nombre} debe ser entero ≥ {minimo}")
        object.__setattr__(self, "occurred_at", _utc("occurred_at", self.occurred_at))
        # Congela el payload en su forma canónica: valida tipos y tamaño una vez.
        cuerpo = canonical_json(self.payload)
        if len(cuerpo.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise EnvelopeError("PAYLOAD_TOO_LARGE",
                                f"El payload supera {MAX_PAYLOAD_BYTES} bytes")
        object.__setattr__(self, "payload", json.loads(cuerpo))
        object.__setattr__(self, "authorization", json.loads(canonical_json(self.authorization)))

    # ── identidad del hecho ──────────────────────────────────────────────
    @property
    def content_hash(self) -> str:
        """Huella de lo que el hecho ES; no incluye secuencia ni datos de envío."""
        hecho = {
            "event_id": self.event_id, "operation_id": self.operation_id,
            "event_type": self.event_type, "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type, "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version, "branch_id": self.branch_id,
            "actor_id": self.actor_id, "occurred_at": self.occurred_at,
            "payload": self.payload,
        }
        return hashlib.sha256(canonical_json(hecho).encode("utf-8")).hexdigest()

    # ── serialización ────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_version": self.envelope_version,
            "event_id": self.event_id, "operation_id": self.operation_id,
            "event_type": self.event_type, "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type, "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version,
            "branch_id": self.branch_id, "workstation_id": self.workstation_id,
            "sequence_no": self.sequence_no, "actor_id": self.actor_id,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id, "causation_id": self.causation_id,
            "authorization": dict(self.authorization),
            "payload": dict(self.payload),
            "content_hash": self.content_hash,
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReplicationEnvelope":
        """Lee un sobre recibido. Verifica versión y huella antes de aceptarlo."""
        if not isinstance(data, Mapping):
            raise EnvelopeError("MALFORMED", "El sobre no es un objeto")
        version = data.get("envelope_version")
        if version not in SUPPORTED_ENVELOPE_VERSIONS:
            raise EnvelopeError("ENVELOPE_VERSION_UNSUPPORTED",
                                f"Versión de sobre {version!r} no soportada")
        faltan = [k for k in ("event_id", "operation_id", "event_type", "schema_version",
                              "aggregate_type", "aggregate_id", "aggregate_version",
                              "branch_id", "workstation_id", "sequence_no", "occurred_at",
                              "payload", "content_hash") if k not in data]
        if faltan:
            raise EnvelopeError("MALFORMED", "Faltan campos: " + ", ".join(faltan))
        try:
            instante = datetime.fromisoformat(str(data["occurred_at"]))
        except ValueError as exc:
            raise EnvelopeError("MALFORMED", f"occurred_at inválido: {exc}") from exc
        sobre = cls(
            event_id=data["event_id"], operation_id=data["operation_id"],
            event_type=data["event_type"], schema_version=data["schema_version"],
            aggregate_type=data["aggregate_type"], aggregate_id=data["aggregate_id"],
            aggregate_version=data["aggregate_version"], branch_id=data["branch_id"],
            workstation_id=data["workstation_id"], sequence_no=data["sequence_no"],
            occurred_at=instante, payload=data["payload"] or {},
            actor_id=data.get("actor_id"), correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            authorization=data.get("authorization") or {}, envelope_version=version)
        if sobre.content_hash != data["content_hash"]:
            raise EnvelopeError("CONTENT_HASH_MISMATCH",
                                "La huella no corresponde al contenido del sobre")
        return sobre

    @classmethod
    def from_json(cls, text: str) -> "ReplicationEnvelope":
        try:
            # Un número con decimales fuera de texto nunca se convierte en
            # float: el contrato lo rechaza al leerlo (dinero = Decimal en texto).
            datos = json.loads(text, parse_float=_reject_float)
        except EnvelopeError:
            raise
        except ValueError as exc:
            raise EnvelopeError("MALFORMED", f"JSON inválido: {exc}") from exc
        return cls.from_dict(datos)


def _reject_float(texto: str):
    raise EnvelopeError("FLOAT_NOT_ALLOWED",
                        f"Número con decimales ({texto}) fuera de texto: use Decimal como texto")


# ── desde el outbox de un contexto ──────────────────────────────────────────
def envelope_from_outbox_event(event: Mapping[str, Any], *, aggregate_type: str,
                               aggregate_version: int, workstation_id: str,
                               sequence_no: int, schema_version: int = 1,
                               correlation_id: str | None = None,
                               causation_id: str | None = None,
                               authorization: Mapping[str, Any] | None = None,
                               ) -> ReplicationEnvelope:
    """Envuelve el evento canónico que un contexto guardó en su outbox
    (`event_id`, `event_name`, `operation_id`, `entity_id`, `branch_id`,
    `user_id`, `timestamp`, `payload`: la forma de `cash_event_payload`,
    `commercial_instrument_event_payload` y demás constructores)."""
    try:
        instante = datetime.fromisoformat(str(event["timestamp"]))
    except (KeyError, ValueError) as exc:
        raise EnvelopeError("MALFORMED", f"Evento sin timestamp válido: {exc}") from exc
    if instante.tzinfo is None:
        raise EnvelopeError("NAIVE_DATETIME", "El evento del outbox no tiene zona horaria")
    return ReplicationEnvelope(
        event_id=event.get("event_id"), operation_id=event.get("operation_id"),
        event_type=event.get("event_name"), schema_version=schema_version,
        aggregate_type=aggregate_type, aggregate_id=event.get("entity_id"),
        aggregate_version=aggregate_version, branch_id=event.get("branch_id"),
        workstation_id=workstation_id, sequence_no=sequence_no, occurred_at=instante,
        payload=event.get("payload") or {}, actor_id=event.get("user_id") or None,
        correlation_id=correlation_id or event.get("correlation_id"),
        causation_id=causation_id or event.get("causation_id"),
        authorization=authorization or {})


# ── respuesta del servidor ──────────────────────────────────────────────────
class ReplicationOutcome(str, Enum):
    #: Aplicado ahora.
    ACCEPTED = "ACCEPTED"
    #: Ya estaba aplicado con la MISMA huella: la estación lo da por confirmado.
    DUPLICATE = "DUPLICATE"
    #: Contradice el estado central (versión, huella distinta, regla de negocio
    #: compartida). Queda visible para resolverse; nunca se pisa.
    CONFLICT = "CONFLICT"
    #: Permanente (contrato inválido, sin permiso): a revisión, no se reintenta.
    REJECTED = "REJECTED"
    #: Transitorio (servidor ocupado, dependencia caída): se reintenta.
    RETRY = "RETRY"

    @property
    def settles(self) -> bool:
        """¿La estación puede dejar de enviarlo?"""
        return self in (ReplicationOutcome.ACCEPTED, ReplicationOutcome.DUPLICATE)


@dataclass(frozen=True)
class ReplicationAck:
    event_id: str
    outcome: ReplicationOutcome
    error_code: str = ""
    message: str = ""
    remote_revision: str = ""
    conflict: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_uuid("event_id", self.event_id)
        object.__setattr__(self, "outcome", ReplicationOutcome(self.outcome))
        if self.outcome in (ReplicationOutcome.CONFLICT, ReplicationOutcome.REJECTED,
                            ReplicationOutcome.RETRY) and not self.error_code:
            raise EnvelopeError("MALFORMED_ACK",
                                f"Un acuse {self.outcome.value} necesita error_code")

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "outcome": self.outcome.value,
                "error_code": self.error_code, "message": self.message,
                "remote_revision": self.remote_revision,
                "conflict": None if self.conflict is None else dict(self.conflict)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReplicationAck":
        try:
            return cls(event_id=data["event_id"], outcome=data["outcome"],
                       error_code=data.get("error_code") or "",
                       message=data.get("message") or "",
                       remote_revision=data.get("remote_revision") or "",
                       conflict=data.get("conflict"))
        except (KeyError, ValueError) as exc:
            if isinstance(exc, EnvelopeError):
                raise
            raise EnvelopeError("MALFORMED_ACK", f"Acuse inválido: {exc}") from exc


__all__ = [
    "ENVELOPE_VERSION", "EnvelopeError", "MAX_PAYLOAD_BYTES", "ReplicationAck",
    "ReplicationEnvelope", "ReplicationOutcome", "SUPPORTED_ENVELOPE_VERSIONS",
    "canonical_json", "envelope_from_outbox_event",
]
