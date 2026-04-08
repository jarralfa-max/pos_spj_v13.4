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

    # FASE WA: handlers para orquestación WhatsApp ↔ ERP
    _wire_wa_events(bus, container)

    # v13.4: handlers financieros para merma y compras
    _wire_merma_financiero(bus, container)
    _wire_purchase_inventario(bus, container)

    # v13.4: asiento ingreso en venta + ajuste stock en merma
    _wire_venta_financiero(bus, container)
    _wire_merma_inventario(bus, container)
    _wire_flujos_criticos(bus, container)

    logger.info("EventBus wiring completado — %d eventos activos",
                len(bus.registered_events()))


def _wire_flujos_criticos(bus, container) -> None:
    """
    Wiring mínimo solicitado por operación:
      VENTA_COMPLETADA   -> inventory/finance
      COMPRA_REGISTRADA  -> inventory/finance
      MERMA_REGISTRADA   -> inventory/finance
    Implementación aditiva y defensiva (no rompe wiring previo).
    """
    from core.events.event_bus import (
        VENTA_COMPLETADA, COMPRA_REGISTRADA, MERMA_CREATED
    )

    def _venta_stock(data: dict) -> None:
        inv = getattr(container, "inventory_service", None)
        if not inv or not hasattr(inv, "descontar_stock"):
            return
        for item in data.get("items", []):
            try:
                inv.descontar_stock(
                    producto_id=item.get("producto_id"),
                    cantidad=float(item.get("cantidad", 0)),
                    branch_id=data.get("sucursal_id", 1),
                    referencia_id=data.get("venta_id", "VENTA"),
                    usuario=data.get("usuario", "sistema"),
                    operation_id=data.get("operation_id"),
                )
            except Exception:
                continue

    def _compra_stock(data: dict) -> None:
        inv = getattr(container, "inventory_service", None)
        if not inv or not hasattr(inv, "incrementar_stock"):
            return
        for item in data.get("items", []):
            try:
                inv.incrementar_stock(
                    producto_id=item.get("producto_id"),
                    cantidad=float(item.get("cantidad", 0)),
                    unit_cost=float(item.get("costo_unitario", item.get("unit_cost", 0))),
                    branch_id=data.get("sucursal_id", 1),
                    referencia_id=data.get("compra_id", "COMPRA"),
                    usuario=data.get("usuario", "sistema"),
                    operation_id=data.get("operation_id"),
                )
            except Exception:
                continue

    def _compra_egreso(data: dict) -> None:
        fs = getattr(container, "finance_service", None)
        if not fs or not hasattr(fs, "registrar_egreso"):
            return
        fs.registrar_egreso(
            concepto=f"Compra #{data.get('compra_id', '')}",
            monto=float(data.get("total", data.get("monto", 0))),
            referencia_id=data.get("compra_id"),
            usuario_id=data.get("usuario_id"),
            sucursal_id=data.get("sucursal_id", 1),
            metadata={"proveedor_id": data.get("proveedor_id")},
        )

    def _merma_perdida(data: dict) -> None:
        fs = getattr(container, "finance_service", None)
        if not fs or not hasattr(fs, "registrar_perdida"):
            return
        fs.registrar_perdida(
            concepto=f"Merma #{data.get('merma_id', '')}",
            monto=float(data.get("valor", data.get("costo", 0))),
            referencia_id=data.get("merma_id"),
            usuario_id=data.get("usuario_id"),
            sucursal_id=data.get("sucursal_id", 1),
            metadata={"producto_id": data.get("producto_id")},
        )

    bus.subscribe(VENTA_COMPLETADA, _venta_stock, priority=45, label="venta_stock_critico")
    bus.subscribe(COMPRA_REGISTRADA, _compra_stock, priority=45, label="compra_stock_critico")
    bus.subscribe(COMPRA_REGISTRADA, _compra_egreso, priority=45, label="compra_egreso_critico")
    bus.subscribe(MERMA_CREATED, _merma_perdida, priority=45, label="merma_perdida_critico")


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


# ── WA Events (FASE WA) ───────────────────────────────────────────────────────

def _wire_wa_events(bus, container) -> None:
    """
    Conecta eventos del microservicio WA al ERP:
      SALE_CREATED      → audit + BI cache invalidation
      PAYMENT_RECEIVED  → audit + treasury
      PURCHASE_ORDER_CREATED → audit + notificación
    """
    # Importar constantes del bus WA (definidas en erp/events.py del microservicio
    # pero también como strings normales — no necesita importar el módulo WA)
    SALE_CREATED_WA        = "SALE_CREATED"
    PAYMENT_RECEIVED_WA    = "PAYMENT_RECEIVED"
    PURCHASE_ORDER_WA      = "PURCHASE_ORDER_CREATED"
    STAFF_NOTIFICATION_WA  = "STAFF_NOTIFICATION"
    FORECAST_DEMAND_WA     = "FORECAST_DEMAND_UPDATED"

    def _on_sale_created(data: dict) -> None:
        """Registra en audit_logs cuando se crea una venta desde WA."""
        if data.get("canal") != "whatsapp":
            return  # Solo procesar ventas WA (evitar loops con VENTA_COMPLETADA)
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('CREADA','VENTAS_WA','ventas',?,?,?,?,datetime('now'))",
                (
                    data.get("venta_id"),
                    data.get("cliente_id", 0),
                    data.get("sucursal_id", 1),
                    f"Folio={data.get('folio','')} Total=${float(data.get('total',0)):.2f} origen={data.get('origen','wa')}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
            # Invalidar caché BI
            bi = getattr(container, "bi_service", None)
            if bi:
                getattr(bi, "invalidar_cache", lambda *a: None)(
                    data.get("sucursal_id", 1))
        except Exception as e:
            logger.debug("on_sale_created: %s", e)

    def _on_payment_received(data: dict) -> None:
        """Registra el pago recibido en audit + tesorería."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('PAGO_RECIBIDO','WA_PAGOS','anticipos',?,?,?,?,datetime('now'))",
                (
                    data.get("venta_id"),
                    data.get("telefono", "cliente_wa"),
                    data.get("sucursal_id", 1),
                    f"Folio={data.get('folio','')} Monto=${float(data.get('monto',0)):.2f} metodo={data.get('metodo','')}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("on_payment_received: %s", e)

    def _on_purchase_order(data: dict) -> None:
        """Audita generación automática de OC desde WA."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('OC_AUTOMATICA','COMPRAS','ordenes_compra',?,?,?,?,datetime('now'))",
                (
                    data.get("oc_id"),
                    "wa_orchestrator",
                    data.get("sucursal_id", 1),
                    f"Producto={data.get('nombre','')} Cant={data.get('cantidad',0)} venta={data.get('venta_id',0)}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("on_purchase_order: %s", e)

    def _on_staff_notification(data: dict) -> None:
        """Reenvía notificaciones de staff via WhatsAppService del ERP."""
        try:
            ws = getattr(container, "whatsapp_service", None)
            if not ws:
                return
            phones = data.get("phones", [])
            mensaje = data.get("mensaje", "")
            if not mensaje or not phones:
                return
            for phone in phones[:5]:  # Máximo 5 destinatarios por evento
                try:
                    ws.send_message(phone_number=phone, message=mensaje)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("on_staff_notification: %s", e)

    def _on_forecast_demand(data: dict) -> None:
        """Pasa demanda WA al ForecastService del ERP (SOLO LECTURA — no ejecuta)."""
        try:
            fs = getattr(container, "actionable_forecast", None)
            if fs and hasattr(fs, "registrar_demanda_wa"):
                fs.registrar_demanda_wa(
                    producto_id=data.get("producto_id"),
                    cantidad=data.get("demanda_est", 0),
                    periodo=data.get("periodo", ""),
                )
        except Exception as e:
            logger.debug("on_forecast_demand: %s", e)

    bus.subscribe(SALE_CREATED_WA,       _on_sale_created,     priority=30, label="wa_sale_audit")
    bus.subscribe(PAYMENT_RECEIVED_WA,   _on_payment_received, priority=30, label="wa_payment_audit")
    bus.subscribe(PURCHASE_ORDER_WA,     _on_purchase_order,   priority=30, label="wa_oc_audit")
    bus.subscribe(STAFF_NOTIFICATION_WA, _on_staff_notification, priority=10, label="wa_staff_notify")
    bus.subscribe(FORECAST_DEMAND_WA,    _on_forecast_demand,  priority=5,  label="wa_forecast_demand")


# ── v13.4 handlers: MERMA_CREATED + PURCHASE_CREATED ─────────────────────────

def _wire_merma_financiero(bus, container) -> None:
    """
    MERMA_CREATED → asiento contable doble entrada.
    Debita cuenta_mermas, acredita cuenta_inventario.
    Solo se activa si finance_service está disponible en el container.
    """
    from core.events.event_bus import MERMA_CREATED

    def _on_merma_financiero(data: dict) -> None:
        try:
            fs = getattr(container, "finance_service", None)
            if not fs or not hasattr(fs, "registrar_asiento"):
                return
            valor = float(data.get("valor", data.get("costo", 0)))
            if valor <= 0:
                return
            fs.registrar_asiento(
                debe="mermas_y_deterioro",
                haber="inventario_almacen",
                concepto=f"Merma: {data.get('motivo', 'N/A')} — producto {data.get('producto_id', '')}",
                monto=abs(valor),
                modulo="merma",
                referencia_id=data.get("merma_id") or data.get("producto_id"),
                usuario_id=data.get("usuario_id"),
                sucursal_id=data.get("sucursal_id", 1),
                evento="MERMA_REGISTRADA",
                metadata={
                    "producto_id": data.get("producto_id"),
                    "cantidad": data.get("cantidad"),
                    "motivo": data.get("motivo"),
                },
            )
        except Exception as e:
            logger.debug("on_merma_financiero: %s", e)

    bus.subscribe(MERMA_CREATED, _on_merma_financiero,
                  priority=50, label="merma_ledger")


def _wire_purchase_inventario(bus, container) -> None:
    """
    PURCHASE_CREATED → incrementa stock + auditoría.
    Complementa el handler de sync de COMPRA_REGISTRADA ya existente.
    Registra asiento: inventario_almacen (debe) ↔ cuentas_por_pagar (haber).
    """
    from core.events.event_bus import PURCHASE_CREATED

    def _on_compra_inventario(data: dict) -> None:
        try:
            fs = getattr(container, "finance_service", None)
            if not fs or not hasattr(fs, "registrar_asiento"):
                return
            total = float(data.get("total", data.get("monto", 0)))
            if total <= 0:
                return
            fs.registrar_asiento(
                debe="inventario_almacen",
                haber="cuentas_por_pagar",
                concepto=f"Compra #{data.get('compra_id', '')} — proveedor {data.get('proveedor_id', '')}",
                monto=total,
                modulo="compras",
                referencia_id=data.get("compra_id"),
                usuario_id=data.get("usuario_id"),
                sucursal_id=data.get("sucursal_id", 1),
                evento="COMPRA_REGISTRADA",
                metadata={
                    "proveedor_id": data.get("proveedor_id"),
                    "items": data.get("items", []),
                },
            )
        except Exception as e:
            logger.debug("on_compra_inventario: %s", e)

    bus.subscribe(PURCHASE_CREATED, _on_compra_inventario,
                  priority=80, label="compra_ledger")


# ── v13.4: VENTA_COMPLETADA → asiento ingreso ────────────────────────────────

def _wire_venta_financiero(bus, container) -> None:
    """
    VENTA_COMPLETADA → asiento contable de ingreso doble entrada.
    Debita caja_ventas, acredita ventas_contado.
    Solo activo si finance_service.registrar_ingreso está disponible.
    """
    from core.events.event_bus import VENTA_COMPLETADA

    def _on_venta_ingreso(data: dict) -> None:
        try:
            fs = getattr(container, "finance_service", None)
            if not fs or not hasattr(fs, "registrar_ingreso"):
                return
            total = float(data.get("total", 0))
            if total <= 0:
                return
            fs.registrar_ingreso(
                concepto=f"Venta #{data.get('folio', data.get('venta_id', ''))}",
                monto=total,
                referencia_id=data.get("venta_id"),
                usuario_id=data.get("usuario_id"),
                sucursal_id=data.get("sucursal_id", 1),
                metadata={"folio": data.get("folio"),
                          "cliente_id": data.get("cliente_id")},
            )
        except Exception as e:
            logger.debug("on_venta_ingreso: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _on_venta_ingreso,
                  priority=50, label="venta_ledger")


# ── v13.4: MERMA_CREATED → ajuste stock físico ───────────────────────────────

def _wire_merma_inventario(bus, container) -> None:
    """
    MERMA_CREATED → descuenta la cantidad merma del stock físico.
    Complementa _wire_merma_financiero (que solo registra el asiento).
    Solo activo si inventory_service.ajustar_merma está disponible.
    """
    from core.events.event_bus import MERMA_CREATED

    def _on_merma_inventario(data: dict) -> None:
        try:
            inv = getattr(container, "inventory_service", None)
            if not inv or not hasattr(inv, "ajustar_merma"):
                return
            cantidad = float(data.get("cantidad", 0))
            if cantidad <= 0:
                return
            inv.ajustar_merma(
                producto_id=data.get("producto_id"),
                cantidad=cantidad,
                branch_id=data.get("sucursal_id", 1),
                referencia_id=str(data.get("merma_id", "MERMA")),
                usuario=data.get("usuario", "sistema"),
            )
        except Exception as e:
            logger.debug("on_merma_inventario: %s", e)

    bus.subscribe(MERMA_CREATED, _on_merma_inventario,
                  priority=80, label="merma_stock")
