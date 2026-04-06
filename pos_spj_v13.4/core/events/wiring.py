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

    # FASE 12: handlers cruzados para servicios inteligentes
    _wire_alertas(bus, container)
    _wire_finanzas(bus, container)
    _wire_rrhh(bus, container)
    _wire_precio_margen(bus, container)

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


# ── ALERT_CRITICAL ────────────────────────────────────────────────────────────

def _wire_alertas(bus, container) -> None:
    from core.events.event_bus import ALERT_CRITICAL

    def _notify_alert_critical(data: dict) -> None:
        """Enruta ALERT_CRITICAL al NotificationService (FASE 12)."""
        severity = data.get("severity", "")
        if severity not in ("high", "critical"):
            return
        try:
            ns = getattr(container, "notification_service", None)
            if ns and hasattr(ns, "notificar_alerta_critica"):
                ns.notificar_alerta_critica(
                    titulo=data.get("title", "Alerta crítica"),
                    mensaje=data.get("message", ""),
                    sucursal_id=data.get("sucursal_id", 1),
                )
        except Exception as e:
            logger.warning("notify_alert_critical: %s", e)

    bus.subscribe(ALERT_CRITICAL, _notify_alert_critical,
                  priority=10, label="notify_alert_critical")


# ── MOVIMIENTO_FINANCIERO ─────────────────────────────────────────────────────

def _wire_finanzas(bus, container) -> None:
    from core.events.event_bus import MOVIMIENTO_FINANCIERO

    def _audit_movimiento(data: dict) -> None:
        """Audita cada movimiento financiero para trazabilidad (FASE 12)."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (
                    data.get("tipo", "MOVIMIENTO"),
                    "TESORERIA",
                    "movimientos_caja",
                    None,
                    data.get("referencia", "sistema"),
                    data.get("sucursal_id", 1),
                    f"Concepto={data.get('concepto','')} Monto=${float(data.get('monto',0)):.2f}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit_movimiento handler: %s", e)

    bus.subscribe(MOVIMIENTO_FINANCIERO, _audit_movimiento,
                  priority=30, label="audit_movimiento_financiero")


# ── RRHH: EMPLOYEE_OVERWORK / PAYROLL_DUE ────────────────────────────────────

def _wire_rrhh(bus, container) -> None:
    from core.events.event_bus import EMPLOYEE_OVERWORK, PAYROLL_DUE

    def _notify_overwork(data: dict) -> None:
        """Notifica por WhatsApp cuando un empleado supera días consecutivos (FASE 12)."""
        try:
            ws = getattr(container, "whatsapp_service", None)
            if not ws:
                return
            tel_row = container.db.execute(
                "SELECT telefono FROM configuraciones WHERE clave='tel_gerente_rrhh' LIMIT 1"
            ).fetchone()
            if not tel_row or not tel_row[0]:
                return
            nombre = data.get("nombre", f"Empleado #{data.get('empleado_id')}")
            dias = data.get("dias_consecutivos", "?")
            msg = (f"RRHH: {nombre} lleva {dias} días consecutivos trabajando. "
                   f"Programar descanso obligatorio (NOM-035).")
            ws.send_message(phone_number=tel_row[0], message=msg)
        except Exception as e:
            logger.debug("notify_overwork: %s", e)

    def _notify_payroll_due(data: dict) -> None:
        """Notifica cuando una nómina está por vencer (FASE 12)."""
        try:
            ws = getattr(container, "whatsapp_service", None)
            if not ws:
                return
            tel_row = container.db.execute(
                "SELECT telefono FROM configuraciones WHERE clave='tel_gerente_rrhh' LIMIT 1"
            ).fetchone()
            if not tel_row or not tel_row[0]:
                return
            nombre = data.get("nombre", f"Empleado #{data.get('empleado_id')}")
            dias = data.get("dias_vencimiento", "?")
            msg = f"RRHH: Nómina de {nombre} vence en {dias} días. Procesar pago."
            ws.send_message(phone_number=tel_row[0], message=msg)
        except Exception as e:
            logger.debug("notify_payroll_due: %s", e)

    bus.subscribe(EMPLOYEE_OVERWORK, _notify_overwork,
                  priority=10, label="notify_overwork_wa")
    bus.subscribe(PAYROLL_DUE, _notify_payroll_due,
                  priority=10, label="notify_payroll_due_wa")


# ── PRICE_BELOW_MARGIN ────────────────────────────────────────────────────────

def _wire_precio_margen(bus, container) -> None:
    from core.events.event_bus import PRICE_BELOW_MARGIN

    def _on_price_below_margin(data: dict) -> None:
        """Registra en audit_logs cuando se vende por debajo del margen (FASE 12)."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('PRECIO_BAJO_MARGEN','VENTAS','productos',?,?,?,?,datetime('now'))",
                (
                    data.get("producto_id"),
                    data.get("usuario", "cajero"),
                    data.get("sucursal_id", 1),
                    (f"Precio=${float(data.get('precio_venta',0)):.2f} "
                     f"Costo=${float(data.get('costo',0)):.2f} "
                     f"Margen={float(data.get('margen_pct',0)):.1f}%"),
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("price_below_margin handler: %s", e)

    bus.subscribe(PRICE_BELOW_MARGIN, _on_price_below_margin,
                  priority=30, label="audit_price_below_margin")
