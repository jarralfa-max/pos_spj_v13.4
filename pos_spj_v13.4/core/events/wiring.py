# core/events/wiring.py — SPJ POS v13.3
"""
Cableado central de handlers al EventBus.

Extraído de AppContainer._wire_event_bus() para:
  1. Reducir el tamaño del AppContainer
  2. Hacer explícitas las dependencias entre eventos y handlers
  3. Permitir testing independiente de cada handler

Se ejecuta una vez desde AppContainer.__init__() al final:
    from core.events.wiring import wire_all
    wire_all(self)

Convención de prioridades:
  100+  Sync (CRÍTICO — debe ejecutarse primero y de forma síncrona)
   50   Lógica de negocio (fidelidad, comisiones, etc.)
   30   Auditoría
   10   Notificaciones (soft-fail, no crítico)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.app_container import AppContainer

logger = logging.getLogger("spj.events.wiring")


def wire_all(container: "AppContainer") -> None:
    """Registra todos los handlers del EventBus."""
    from core.events.event_bus import get_bus

    bus = get_bus()

    _wire_venta(bus, container)
    _wire_pedido(bus, container)
    _wire_inventario(bus, container)
    _wire_produccion(bus, container)

    logger.info("EventBus wiring completado — %d eventos activos",
                len(bus.registered_events()))


# ── VENTA_COMPLETADA ──────────────────────────────────────────────────────────

def _wire_venta(bus, container) -> None:
    from core.events.event_bus import VENTA_COMPLETADA

    # Prioridad 100: Sync (CRÍTICO)
    def _sync_venta(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="VENTA_COMPLETADA",
                entidad="ventas",
                entidad_id=data.get("venta_id"),
                payload=data.get("data", data),
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("usuario", "Sistema"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.error("sync_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _sync_venta,
                  priority=100, label="sync_venta")

    # Prioridad 50: Fidelidad
    def _loyalty_venta(data: dict) -> None:
        cliente_id = data.get("cliente_id")
        if not cliente_id:
            return
        try:
            ls = getattr(container, "loyalty_service", None)
            if ls:
                ls.process_loyalty_for_sale(
                    client_id=cliente_id,
                    total_sale=float(data.get("total", 0)),
                    branch_id=data.get("sucursal_id", 1),
                )
        except Exception as e:
            logger.warning("loyalty_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _loyalty_venta,
                  priority=50, label="loyalty_venta")

    # Prioridad 30: Auditoría
    def _audit_venta(data: dict) -> None:
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('COMPLETADA','VENTAS','ventas',?,?,?,?,datetime('now'))",
                (
                    data.get("venta_id"),
                    data.get("usuario", "cajero"),
                    data.get("sucursal_id", 1),
                    f"Folio={data.get('folio', '')} Total=${float(data.get('total', 0)):.2f}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _audit_venta,
                  priority=30, label="audit_venta")


# ── PEDIDO_NUEVO ──────────────────────────────────────────────────────────────

def _wire_pedido(bus, container) -> None:
    from core.events.event_bus import PEDIDO_NUEVO

    def _sync_pedido(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="PEDIDO_NUEVO",
                entidad="pedidos_whatsapp",
                entidad_id=data.get("pedido_id"),
                payload=data,
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("telefono", "bot"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.error("sync_pedido handler: %s", e)

    bus.subscribe(PEDIDO_NUEVO, _sync_pedido,
                  priority=100, label="sync_pedido")

    def _audit_pedido(data: dict) -> None:
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('NUEVO','PEDIDOS_WA','pedidos_whatsapp',?,?,?,?,datetime('now'))",
                (
                    data.get("pedido_id"),
                    data.get("telefono", "bot"),
                    data.get("sucursal_id", 1),
                    f"Total=${float(data.get('total', 0)):.2f} #{data.get('numero', '')}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit_pedido handler: %s", e)

    bus.subscribe(PEDIDO_NUEVO, _audit_pedido,
                  priority=30, label="audit_pedido")


# ── INVENTARIO ────────────────────────────────────────────────────────────────

def _wire_inventario(bus, container) -> None:
    from core.events.event_bus import STOCK_BAJO_MINIMO, AJUSTE_INVENTARIO

    def _on_stock_bajo(data: dict) -> None:
        logger.warning(
            "Stock bajo: producto=%s sucursal=%s stock=%.3f minimo=%.3f",
            data.get("producto_id"),
            data.get("sucursal_id"),
            data.get("stock_actual", 0),
            data.get("stock_minimo", 0),
        )
        # Notificar si el servicio está disponible
        try:
            ns = getattr(container, "notification_service", None)
            if ns:
                ns.notificar_stock_bajo(
                    [data], sucursal_id=data.get("sucursal_id", 1)
                )
        except Exception:
            pass

    bus.subscribe(STOCK_BAJO_MINIMO, _on_stock_bajo,
                  priority=50, label="log_stock_bajo")

    # Sync para ajustes de inventario
    def _sync_ajuste(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="AJUSTE_INVENTARIO",
                entidad="movimientos_inventario",
                entidad_id=data.get("movimiento_id"),
                payload=data,
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("usuario", "Sistema"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.debug("sync_ajuste handler: %s", e)

    bus.subscribe(AJUSTE_INVENTARIO, _sync_ajuste,
                  priority=100, label="sync_ajuste")


# ── PRODUCCIÓN ────────────────────────────────────────────────────────────────

def _wire_produccion(bus, container) -> None:
    from core.events.event_bus import PRODUCCION_COMPLETADA

    def _sync_produccion(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="PRODUCCION_COMPLETADA",
                entidad="production_batches",
                entidad_id=data.get("batch_id"),
                payload=data,
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("usuario", "produccion"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.debug("sync_produccion handler: %s", e)

    bus.subscribe(PRODUCCION_COMPLETADA, _sync_produccion,
                  priority=100, label="sync_produccion")
