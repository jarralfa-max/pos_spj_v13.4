# core/domain/events.py — SPJ POS v13.3
"""
Contrato base para eventos de dominio.

Cada evento de dominio DEBE tener:
  - event_id:       UUID único (generado automáticamente)
  - event_type:     nombre canónico del evento
  - timestamp:      UTC ISO 8601
  - sucursal_id:    origen
  - origin_device:  UUID del dispositivo (para sync)
  - payload_hash:   SHA256 del payload (idempotencia)
  - operation_id:   agrupa el evento con sus efectos secundarios

Uso:
    from core.domain.events import DomainEvent

    event = DomainEvent(
        event_type="VENTA_COMPLETADA",
        sucursal_id=1,
        usuario="cajero01",
        data={"venta_id": 42, "folio": "V-001", "total": 350.00},
    )
    bus.publish(event.event_type, event.to_dict())
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class DomainEvent:
    """
    Evento inmutable de dominio.

    frozen=True garantiza que nadie modifique el payload después de creado,
    lo cual es esencial para que payload_hash sea confiable.
    """

    # ── Identidad única del evento
    event_id: str = field(default_factory=_new_uuid)

    # ── Tipo del evento (e.g. VENTA_COMPLETADA, AJUSTE_INVENTARIO)
    event_type: str = ""

    # ── Timestamp UTC ISO 8601 (NO depende del reloj local para sync)
    timestamp: str = field(default_factory=_utc_now)

    # ── Origen: cuál sucursal y dispositivo lo generó
    sucursal_id: int = 1
    origin_device: str = ""  # se llena desde EventLogger._device_id

    # ── Versionado
    event_version: int = 1   # schema version del payload
    device_version: int = 0  # contador monotonic del dispositivo

    # ── Trazabilidad
    operation_id: str = field(default_factory=_new_uuid)
    usuario: str = "Sistema"

    # ── Payload específico del dominio (dict serializable)
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def payload_hash(self) -> str:
        """
        SHA256 del payload para deduplicación.
        Usa sort_keys para que el hash sea determinístico
        independientemente del orden de inserción de las keys.
        """
        raw = json.dumps(self.data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        """
        Serializa el evento completo para publicar al EventBus
        y para persistir en event_log / sync_outbox.
        """
        d = asdict(self)
        d["payload_hash"] = self.payload_hash
        return d

    def __repr__(self) -> str:
        return (
            f"DomainEvent(type={self.event_type!r}, "
            f"id={self.event_id[:8]}..., "
            f"suc={self.sucursal_id}, "
            f"hash={self.payload_hash[:8]}...)"
        )
