# core/events/cash_event_bridge.py — SPJ ERP · Remediación A
"""
Bridge canónico de eventos de CAJA + consumidores de finanzas.

Contexto (DEEP_AUDIT_ALL_MODULES_20260704 · B2):
  El sistema tenía DOS vocabularios de eventos de caja en paralelo y NINGUNO
  con suscriptores:
    - Español (legacy):  CAJA_TURNO_ABIERTO / CAJA_MOVIMIENTO /
                         CAJA_CORTE_Z_GENERADO / CAJA_DIFERENCIA_DETECTADA
                         (emitidos por application/services/caja_application_service)
    - Inglés (canónico): CASH_SHIFT_OPENED / CASH_MOVEMENT_RECORDED /
                         CASH_Z_CUT_GENERATED / CASH_DIFFERENCE_DETECTED
                         (emitidos por backend cash_register_application_service)

Estrategia (una sola fuente de verdad, backend en inglés — SPJ_REFACTOR_SKILL):
  El canal canónico es CASH_* (EventName). Este bridge traduce los eventos
  legacy CAJA_* → CASH_*, normalizando las claves del payload al inglés y
  conservando las originales. Es UNIDIRECCIONAL (CAJA_ → CASH_) para no crear
  ciclos: los consumidores se suscriben SOLO a CASH_*, así que da igual qué
  servicio de caja publique — ambos convergen en el canal canónico.

Consumidores añadidos (NO registran asiento — el asiento de diferencia ya lo
registra CajaApplicationService.generar_corte_z / CierreCajaService, evitar
doble contabilización):
  - CashEventAuditHandler: escribe audit_logs (trazabilidad, antes inexistente).
  El refresh de dashboards/KPIs se hace suscribiendo la UI (finanzas, BI) al
  canal canónico CASH_* directamente.
"""
from __future__ import annotations

import logging
from typing import Callable

from backend.shared.events.event_names import EventName

logger = logging.getLogger("spj.events.cash_bridge")

Publisher = Callable[[str, dict], None]

# Legacy español → canónico inglés
CASH_EVENT_MAP: dict[str, str] = {
    "CAJA_TURNO_ABIERTO":        EventName.CASH_SHIFT_OPENED.value,
    "CAJA_MOVIMIENTO":           EventName.CASH_MOVEMENT_RECORDED.value,
    "CAJA_CORTE_Z_GENERADO":     EventName.CASH_Z_CUT_GENERATED.value,
    "CAJA_DIFERENCIA_DETECTADA": EventName.CASH_DIFFERENCE_DETECTED.value,
}

# Canales canónicos que alimentan a los consumidores/dashboards
CANONICAL_CASH_EVENTS: tuple[str, ...] = tuple(CASH_EVENT_MAP.values())

# Normalización de claves de payload (español legacy → inglés canónico).
# Se conservan SIEMPRE las claves originales; solo se AGREGA el alias inglés.
_KEY_ALIASES: dict[str, str] = {
    "turno_id":      "shift_id",
    "cierre_id":     "cut_id",
    "sucursal_id":   "branch_id",
    "usuario":       "user",
    "fondo_inicial": "opening_amount",
    "monto":         "amount",
    "tipo":          "movement_type",
    "concepto":      "concept",
    "diferencia":    "difference",
    "total_ventas":  "total_sales",
    "esperado":      "expected",
    "contado":       "counted",
}


def normalize_cash_payload(caja_event: str, payload: dict | None) -> dict:
    """Devuelve el payload con claves inglesas añadidas (sin perder las originales)."""
    out = dict(payload or {})
    for src, dst in _KEY_ALIASES.items():
        if src in out and dst not in out:
            out[dst] = out[src]
    # Descartar el event_type del canal legacy: el EventBus reinyectará el
    # canónico al re-publicar, para que los consumidores lo lean correcto.
    out.pop("event_type", None)
    out.setdefault("source_event", caja_event)
    return out


class CashEventBridge:
    """Traduce eventos legacy CAJA_* al canal canónico CASH_* (una sola vía)."""

    LEGACY_EVENTS: tuple[str, ...] = tuple(CASH_EVENT_MAP.keys())

    def __init__(self, publisher: Publisher) -> None:
        self._publisher = publisher

    def handle(self, caja_event: str, payload: dict | None) -> str | None:
        canonical = CASH_EVENT_MAP.get(caja_event)
        if not canonical:
            return None
        try:
            self._publisher(canonical, normalize_cash_payload(caja_event, payload))
        except Exception as exc:  # el bridge nunca rompe el flujo de caja
            logger.debug("CashEventBridge %s→%s: %s", caja_event, canonical, exc)
        return canonical


class CashEventAuditHandler:
    """Escribe una fila de auditoría por cada evento canónico de caja.

    Antes de la Remediación A los eventos de caja no llegaban a ningún audit.
    NO registra asiento contable (la diferencia ya la asienta el servicio de
    caja) — solo trazabilidad.
    """

    _ACCION_POR_EVENTO = {
        EventName.CASH_SHIFT_OPENED.value:       "TURNO_ABIERTO",
        EventName.CASH_MOVEMENT_RECORDED.value:  "MOVIMIENTO",
        EventName.CASH_Z_CUT_GENERATED.value:    "CORTE_Z",
        EventName.CASH_DIFFERENCE_DETECTED.value: "DIFERENCIA_DETECTADA",
    }

    def __init__(self, db) -> None:
        self._db = db

    def handle(self, payload: dict) -> None:
        if self._db is None:
            return
        evento = str((payload or {}).get("event_type") or "")
        accion = self._ACCION_POR_EVENTO.get(evento, "CAJA")
        entidad_id = str(
            (payload or {}).get("cut_id")
            or (payload or {}).get("shift_id")
            or ""
        )
        branch = str((payload or {}).get("branch_id") or "")
        usuario = str((payload or {}).get("user") or "sistema")
        monto = (payload or {}).get("amount", (payload or {}).get("difference", ""))
        detalle = f"evento={evento} monto={monto} concepto={(payload or {}).get('concept','')}"
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (accion, "CAJA", "turnos_caja", entidad_id, usuario, branch, detalle),
            )
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as exc:
            logger.debug("CashEventAuditHandler %s: %s", evento, exc)


def register_cash_event_bridge(bus, container=None) -> CashEventBridge:
    """Suscribe el bridge CAJA_*→CASH_* y el audit handler de caja al bus.

    Idempotente: EventBus.subscribe ignora handlers duplicados.
    """
    bridge = CashEventBridge(publisher=lambda evt, data: bus.publish(evt, data))
    # Prioridad alta: el bridge re-emite el canónico antes que otros handlers
    # legacy que pudieran seguir escuchando el canal español.
    for legacy in CashEventBridge.LEGACY_EVENTS:
        bus.subscribe(
            legacy,
            lambda data, _b=bridge, _e=legacy: _b.handle(_e, data),
            priority=90,
            label=f"cash_bridge_{legacy.lower()}",
        )

    db = getattr(container, "db", None) if container is not None else None
    if db is not None:
        audit = CashEventAuditHandler(db)
        for canonical in CANONICAL_CASH_EVENTS:
            bus.subscribe(
                canonical,
                audit.handle,
                priority=30,
                label=f"cash_audit_{canonical.lower()}",
            )
    logger.debug(
        "Cash event bridge registrado (%d legacy → canónico) + audit",
        len(CashEventBridge.LEGACY_EVENTS),
    )
    return bridge
