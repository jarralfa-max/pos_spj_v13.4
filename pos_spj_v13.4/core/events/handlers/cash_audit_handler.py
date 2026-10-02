# core/events/handlers/cash_audit_handler.py
"""
CashAuditHandler — trazabilidad en audit_logs de cada evento canónico de caja.

Canal único: CASH_* (EventName), emitido SOLO por CashRegisterApplicationService
con operation_id. No existe vocabulario paralelo (los CAJA_* y su bridge se
eliminaron al unificar caja), así que cada operación produce una sola fila.

No registra asiento contable: la diferencia del corte la asienta
CajaApplicationService.generar_corte_z (evitar doble contabilización).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.events.cash_audit")

CASH_AUDIT_EVENTS: tuple[str, ...] = (
    EventName.CASH_SHIFT_OPENED.value,
    EventName.CASH_MOVEMENT_RECORDED.value,
    EventName.CASH_Z_CUT_GENERATED.value,
    EventName.CASH_DIFFERENCE_DETECTED.value,
)

_ACCION_POR_EVENTO: Dict[str, str] = {
    EventName.CASH_SHIFT_OPENED.value: "TURNO_ABIERTO",
    EventName.CASH_MOVEMENT_RECORDED.value: "MOVIMIENTO",
    EventName.CASH_Z_CUT_GENERATED.value: "CORTE_Z",
    EventName.CASH_DIFFERENCE_DETECTED.value: "DIFERENCIA_DETECTADA",
}


class CashAuditHandler:
    """Escribe una fila de audit_logs (id UUIDv7) por evento canónico de caja."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def handle(self, payload: Optional[Dict[str, Any]]) -> None:
        if self._db is None:
            return
        payload = payload or {}
        evento = str(payload.get("event_type") or "")
        accion = _ACCION_POR_EVENTO.get(evento, "CAJA")
        entidad_id = str(
            payload.get("cut_id")
            or payload.get("cierre_id")
            or payload.get("shift_id")
            or ""
        )
        monto = payload.get("amount", payload.get("diferencia", ""))
        detalle = (
            f"evento={evento} operation_id={payload.get('operation_id', '')} "
            f"monto={monto} concepto={payload.get('concept', '')}"
        )
        try:
            self._db.execute(
                "INSERT INTO audit_logs"
                " (id, accion, modulo, entidad, entidad_id, usuario,"
                "  sucursal_id, detalles, fecha)"
                " VALUES (?,?,?,?,?,?,?,?, datetime('now','localtime'))",
                (
                    new_uuid(), accion, "CAJA", "turnos_caja", entidad_id,
                    str(payload.get("user") or "sistema"),
                    str(payload.get("branch_id") or ""), detalle,
                ),
            )
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as exc:
            # Post-commit: la auditoría nunca revierte la operación de caja,
            # pero el fallo queda visible en log (no se oculta con OR IGNORE).
            logger.warning("CashAuditHandler %s: %s", evento, exc)


def register_cash_audit(bus: Any, db: Any) -> CashAuditHandler:
    """Suscribe el handler de auditoría a los eventos canónicos de caja."""
    handler = CashAuditHandler(db)
    for evento in CASH_AUDIT_EVENTS:
        bus.subscribe(
            evento,
            handler.handle,
            priority=30,
            label=f"cash_audit_{evento.lower()}",
        )
    return handler
