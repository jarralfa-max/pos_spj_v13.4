# core/events/catalog_events.py — SPJ ERP v13.4
"""
Ruta canónica ÚNICA para publicar cambios de catálogo (sucursales/productos)
y para propagarlos en caliente a los widgets de la ventana principal.

Reglas:
  - Publicar SIEMPRE después del commit exitoso (los servicios llaman a estas
    funciones fuera/al salir del UnitOfWork). Si la transacción falla, no llegar
    aquí.
  - IDs UUIDv7 como str; jamás enteros.
  - El evento granular (branch_created / product_updated / ...) viaja junto al
    evento agregado (branches_changed / products_changed) para que los módulos
    puedan suscribirse a uno u otro.
  - Los canales legacy UPPERCASE de producto (PRODUCTO_CREADO, ...) se emiten
    también por compatibilidad con los módulos que ya los escuchan.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid
from core.events.domain_events import (
    BRANCH_CREATED,
    BRANCH_DEACTIVATED,
    BRANCH_UPDATED,
    BRANCHES_CHANGED,
    PRODUCT_CREATED,
    PRODUCT_DEACTIVATED,
    PRODUCT_UPDATED,
    PRODUCTS_CHANGED,
)

logger = logging.getLogger("spj.catalog_events")

_BRANCH_EVENT_BY_ACTION = {
    "created": BRANCH_CREATED,
    "updated": BRANCH_UPDATED,
    "deactivated": BRANCH_DEACTIVATED,
}
_PRODUCT_EVENT_BY_ACTION = {
    "created": PRODUCT_CREATED,
    "updated": PRODUCT_UPDATED,
    "deactivated": PRODUCT_DEACTIVATED,
}
_LEGACY_PRODUCT_CHANNEL_BY_ACTION = {
    "created": "PRODUCTO_CREADO",
    "updated": "PRODUCTO_ACTUALIZADO",
    "deactivated": "PRODUCTO_ELIMINADO",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_bus():
    from core.events.event_bus import EventBus
    return EventBus()


def publish_branch_event(
    action: str,
    *,
    branch_id: str,
    branch_name: str,
    active: bool,
    source_module: str,
    operation_id: str = "",
) -> dict:
    """Publica el evento granular de sucursal + BRANCHES_CHANGED (post-commit).

    Nunca lanza: un fallo del bus no debe romper el guardado ya confirmado.
    Devuelve el payload publicado (útil para tests/log).
    """
    if action not in _BRANCH_EVENT_BY_ACTION:
        raise ValueError(f"acción de sucursal desconocida: {action!r}")
    payload = {
        "event_id": new_uuid(),
        "operation_id": operation_id or new_uuid(),
        "branch_id": str(branch_id or ""),
        "branch_name": str(branch_name or ""),
        "active": bool(active),
        "action": action,
        "timestamp": _utc_now_iso(),
        "source_module": source_module,
    }
    try:
        bus = _get_bus()
        bus.publish(_BRANCH_EVENT_BY_ACTION[action], dict(payload))
        bus.publish(BRANCHES_CHANGED, dict(payload))
    except Exception as exc:
        logger.warning("publish_branch_event(%s): %s", action, exc)
    return payload


def publish_product_event(
    action: str,
    *,
    product_id: str,
    product_name: str,
    active: bool,
    source_module: str,
    operation_id: str = "",
    legacy: bool = True,
) -> dict:
    """Publica evento granular de producto + PRODUCTS_CHANGED + canal legacy.

    Nunca lanza: un fallo del bus no debe romper el guardado ya confirmado.
    """
    if action not in _PRODUCT_EVENT_BY_ACTION:
        raise ValueError(f"acción de producto desconocida: {action!r}")
    payload = {
        "event_id": new_uuid(),
        "operation_id": operation_id or new_uuid(),
        "product_id": str(product_id or ""),
        "product_name": str(product_name or ""),
        "active": bool(active),
        "action": action,
        "timestamp": _utc_now_iso(),
        "source_module": source_module,
    }
    try:
        bus = _get_bus()
        bus.publish(_PRODUCT_EVENT_BY_ACTION[action], dict(payload))
        bus.publish(PRODUCTS_CHANGED, dict(payload))
        if legacy:
            # Compatibilidad con módulos suscritos a los canales UPPERCASE.
            bus.publish(
                _LEGACY_PRODUCT_CHANNEL_BY_ACTION[action],
                {"producto_id": payload["product_id"],
                 "nombre": payload["product_name"],
                 **payload},
            )
    except Exception as exc:
        logger.warning("publish_product_event(%s): %s", action, exc)
    return payload


# ── Fan-out a widgets (usado por MainWindow; puro, testeable sin PyQt) ────────

def fan_out_branches_changed(widgets, payload: dict) -> list:
    """Propaga un cambio de catálogo de sucursales a los widgets dados.

    Contrato por widget (en orden de preferencia, solo se llama UNO):
      1. on_branches_changed(payload)
      2. refresh_branches()
    Los errores de un widget no detienen a los demás.
    Devuelve la lista de widgets notificados (para tests/log).
    """
    notified = []
    for widget in widgets:
        try:
            if hasattr(widget, "on_branches_changed"):
                widget.on_branches_changed(payload)
            elif hasattr(widget, "refresh_branches"):
                widget.refresh_branches()
            else:
                continue
            notified.append(widget)
        except Exception as exc:
            logger.warning("fan_out_branches_changed → %s: %s",
                           type(widget).__name__, exc)
    return notified


def fan_out_products_changed(widgets, payload: dict) -> list:
    """Propaga un cambio de catálogo de productos a los widgets dados.

    Contrato por widget (en orden de preferencia, solo se llama UNO):
      1. on_products_changed(payload)
      2. refresh_products()
      3. actualizar_datos()   (fallback pesado, solo si no hay específico)
    """
    notified = []
    for widget in widgets:
        try:
            if hasattr(widget, "on_products_changed"):
                widget.on_products_changed(payload)
            elif hasattr(widget, "refresh_products"):
                widget.refresh_products()
            elif hasattr(widget, "actualizar_datos"):
                widget.actualizar_datos()
            else:
                continue
            notified.append(widget)
        except Exception as exc:
            logger.warning("fan_out_products_changed → %s: %s",
                           type(widget).__name__, exc)
    return notified
