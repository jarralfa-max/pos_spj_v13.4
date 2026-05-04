# core/events/event_bus.py — SPJ POS v13.1
"""
EventBus ligero thread-safe para desacoplar servicios.

Reglas:
  1. Handlers síncronos: < 50ms (badge, cache invalidation)
  2. Handlers async_=True: IO lento (impresión, sync, forecast)
  3. Fallo de un handler NO cancela los demás
  4. Errores siempre se loguean — nunca se tragan silenciosamente
  5. Suscribirse después de publicar NO recibe eventos pasados

Eventos de dominio (v13.1):
  Ventas:     VENTA_COMPLETADA, VENTA_CANCELADA
  Inventario: STOCK_BAJO_MINIMO, AJUSTE_INVENTARIO, PRODUCTO_ACTUALIZADO, PRODUCTO_CREADO
  Pedidos:    PEDIDO_NUEVO, PEDIDO_ACTUALIZADO, PEDIDO_CANCELADO
  Compras:    COMPRA_REGISTRADA, RECEPCION_CONFIRMADA
  Logística:  TRASPASO_INICIADO, TRASPASO_CONFIRMADO
  Producción: PRODUCCION_COMPLETADA, PRODUCCION_INICIADA
  Fidelidad:  TARJETA_ESCANEADA, PUNTOS_ACUMULADOS, NIVEL_CAMBIADO
  Sistema:    SESION_INICIADA, SESION_CERRADA, FORECAST_GENERADO
  BI:         CONCILIACION_DIFERENCIA
  Impresión:  TICKET_IMPRESO, PRINT_FAILED
  Alertas:    ALERT_CRITICAL
  Decisiones: DECISION_URGENTE
  Simulación: SIMULACION_EJECUTADA
  IA:         AI_CONSULTA_REALIZADA
  Franquicia: FRANQUICIA_RANKING_GENERADO, FRANQUICIA_TRANSFERENCIA_SUGERIDA
  RRHH:       EMPLOYEE_OVERWORK, EMPLOYEE_REST_DAY, PAYROLL_GENERATED, PAYROLL_DUE
  Spec (FASE 12): SALE_CREATED (=VENTA_COMPLETADA), STOCK_LOW (=STOCK_BAJO_MINIMO),
                  PRICE_BELOW_MARGIN
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("spj.event_bus")
Handler = Callable[[dict], None]

# ── Constantes de eventos ─────────────────────────────────────────────────────
# Ventas
VENTA_COMPLETADA        = "VENTA_COMPLETADA"
VENTA_CANCELADA         = "VENTA_CANCELADA"
# Inventario
STOCK_BAJO_MINIMO       = "STOCK_BAJO_MINIMO"
AJUSTE_INVENTARIO       = "AJUSTE_INVENTARIO"
PRODUCTO_ACTUALIZADO    = "PRODUCTO_ACTUALIZADO"
PRODUCTO_CREADO         = "PRODUCTO_CREADO"
PRODUCTO_ELIMINADO      = "PRODUCTO_ELIMINADO"
# Pedidos WhatsApp / Delivery
PEDIDO_NUEVO            = "PEDIDO_NUEVO"
PEDIDO_ACTUALIZADO      = "PEDIDO_ACTUALIZADO"
PEDIDO_CANCELADO        = "PEDIDO_CANCELADO"
# Compras / Recepción
COMPRA_REGISTRADA       = "COMPRA_REGISTRADA"
RECEPCION_CONFIRMADA    = "RECEPCION_CONFIRMADA"
# Logística
TRASPASO_INICIADO       = "TRASPASO_INICIADO"
TRASPASO_CONFIRMADO     = "TRASPASO_CONFIRMADO"
TRANSFERENCIA_STOCK     = "TRANSFERENCIA_STOCK"
# Producción
PRODUCCION_COMPLETADA   = "PRODUCCION_COMPLETADA"
PRODUCCION_INICIADA     = "PRODUCCION_INICIADA"
# Fidelidad
TARJETA_ESCANEADA       = "TARJETA_ESCANEADA"
PUNTOS_ACUMULADOS       = "PUNTOS_ACUMULADOS"
NIVEL_CAMBIADO          = "NIVEL_CAMBIADO"
# Proveedores
PROVEEDOR_CREADO        = "PROVEEDOR_CREADO"
PROVEEDOR_ACTUALIZADO   = "PROVEEDOR_ACTUALIZADO"

# Transferencias
TRASPASO_ACTUALIZADO        = "TRASPASO_ACTUALIZADO"

# Finanzas/Tesorería
MOVIMIENTO_FINANCIERO       = "MOVIMIENTO_FINANCIERO"

# Cotizaciones
COTIZACION_ACTUALIZADA      = "COTIZACION_ACTUALIZADA"

# Producción
PRODUCCION_REGISTRADA       = "PRODUCCION_REGISTRADA"

# RRHH
EMPLEADO_ACTUALIZADO        = "EMPLEADO_ACTUALIZADO"

# Clientes
CLIENTE_ACTUALIZADO     = "CLIENTE_ACTUALIZADO"
CLIENTE_CREADO          = "CLIENTE_CREADO"

# Impresión — FASE 1
TICKET_IMPRESO          = "TICKET_IMPRESO"    # job_id, job_type, destination, folio, total
PRINT_FAILED            = "PRINT_FAILED"      # job_id, job_type, destination, error_msg, retries

# Alertas — FASE 4
ALERT_CRITICAL          = "ALERT_CRITICAL"    # category, severity, title, message, data, sucursal_id

# Decisiones — FASE 5
DECISION_URGENTE        = "DECISION_URGENTE"  # tipo, prioridad, titulo, detalle, impacto_estimado, accion_propuesta

# Simulación — FASE 7
SIMULACION_EJECUTADA    = "SIMULACION_EJECUTADA"  # escenario, recomendacion, roi_pct, viable

# IA — FASE 8
AI_CONSULTA_REALIZADA   = "AI_CONSULTA_REALIZADA"  # tipo, pregunta, disponible, tiene_alertas

# Ventas — alias English spec (FASE 12)
SALE_CREATED            = VENTA_COMPLETADA          # alias: spec requires SALE_CREATED

# v13.4 spec aliases — aditivos, no cambian el core
SALE_COMPLETED          = VENTA_COMPLETADA          # alias v13.4 spec
STOCK_UPDATED           = AJUSTE_INVENTARIO         # alias v13.4 spec
PURCHASE_CREATED        = COMPRA_REGISTRADA         # alias v13.4 spec
MERMA_CREATED           = "MERMA_REGISTRADA"        # evento específico de merma v13.4

# Inventario — alias English spec (FASE 12)
STOCK_LOW               = STOCK_BAJO_MINIMO         # alias: spec requires STOCK_LOW

# Márgenes — FASE 12 (spec requires PRICE_BELOW_MARGIN)
PRICE_BELOW_MARGIN      = "PRICE_BELOW_MARGIN"      # producto_id, precio_venta, costo, margen_pct, sucursal_id

# Franquicia — FASE 10
FRANQUICIA_RANKING_GENERADO = "FRANQUICIA_RANKING_GENERADO"  # sucursales_count, top_sucursal, top_utilidad, fecha_desde, fecha_hasta
FRANQUICIA_TRANSFERENCIA_SUGERIDA = "FRANQUICIA_TRANSFERENCIA_SUGERIDA"  # producto, desde_sucursal, hacia_sucursal, cantidad_sugerida

# RRHH — FASE 11
EMPLOYEE_OVERWORK       = "EMPLOYEE_OVERWORK"    # empleado_id, nombre, dias_consecutivos, sucursal_id
EMPLOYEE_REST_DAY       = "EMPLOYEE_REST_DAY"    # empleado_id, nombre, fecha_descanso, sucursal_id
PAYROLL_GENERATED       = "PAYROLL_GENERATED"    # empleado_id, nombre, periodo, total, sucursal_id
PAYROLL_DUE             = "PAYROLL_DUE"          # empleado_id, nombre, dias_vencimiento, sucursal_id

# Sistema
SESION_INICIADA         = "SESION_INICIADA"
SESION_CERRADA          = "SESION_CERRADA"
FORECAST_GENERADO       = "FORECAST_GENERADO"
# BI
CONCILIACION_DIFERENCIA = "CONCILIACION_DIFERENCIA"

# v13.5: ERP Use Cases — additive constants only
NOMINA_PAGADA           = "NOMINA_PAGADA"       # empleado_id, neto, periodo, sucursal_id
CLIENTE_REGISTRADO      = CLIENTE_CREADO        # alias v13.5 backward compat
COMPRA_PROCESADA        = COMPRA_REGISTRADA     # alias v13.5 backward compat

# ── EVENTOS CANÓNICOS ERP (v13.6 - Domain-Driven) ──────────────────────────────
# Eventos unificados y normalizados según auditoría de arquitectura

# Inventario Unificado
STOCK_MOVED             = "STOCK_MOVED"         # UNIFICA: AJUSTE_INVENTARIO, PRODUCTO_ACTUALIZADO, etc.
                                                # payload: {product_id, qty_delta, type: 'in'|'out'|'xfer'|'adjust'|'sale'|'purchase'|'production'|'waste', ref_id, branch_id}

STOCK_LEVEL_CRITICAL    = "STOCK_LEVEL_CRITICAL" # Nuevo: threshold breach para auto-reordering
                                                # payload: {product_id, current_qty, threshold, branch_id}

# Producción
PRODUCTION_ORDER_COMPLETED = "PRODUCTION_ORDER_COMPLETED"  # Reemplaza PRODUCCION_COMPLETADA con yield tracking
                                                # payload: {order_id, recipe_id, expected_yield, actual_yield, ingredients_used[], branch_id}

RECIPE_DEVIATION_DETECTED = "RECIPE_DEVIATION_DETECTED"   # Nuevo: variance alert
                                                # payload: {order_id, variance_pct, missing_ingredients[], severity}

# Compras
PURCHASE_ORDER_RECEIVED = "PURCHASE_ORDER_RECEIVED"        # Reemplaza COMPRA_REGISTRADA con recepción formal
                                                # payload: {po_id, vendor_id, items_received[], discrepancies[], total_cost}

ACCOUNT_PAYABLE_CREATED = "ACCOUNT_PAYABLE_CREATED"        # Nuevo: CxC de compras
                                                # payload: {cxp_id, vendor_id, po_id, due_date, amount}

# Ventas (alias adicionales para consistencia)
SALE_CANCELLED          = VENTA_CANCELADA       # alias explícito

# Finanzas
PAYMENT_REGISTERED      = "PAYMENT_REGISTERED"  # UNIFICA: MOVIMIENTO_FINANCIERO para pagos
                                                # payload: {transaction_id, amount, method, direction: 'in'|'out', entity_id, entity_type}

ACCOUNT_RECEIVABLE_CREATED = "ACCOUNT_RECEIVABLE_CREATED"  # Nuevo: CxC de ventas crédito
                                                # payload: {cxc_id, customer_id, sale_id, due_date, amount}

# Lealtad
LOYALTY_POINTS_ACCUMULATED = "LOYALTY_POINTS_ACCUMULATED"  # Alias explícito para PUNTOS_ACUMULADOS
LOYALTY_POINTS_REDEEMED    = "LOYALTY_POINTS_REDEEMED"     # Nuevo: redención explícita
                                                # payload: {customer_id, points, discount_applied, source_sale_id}

CUSTOMER_TIER_CHANGED   = "CUSTOMER_TIER_CHANGED"          # Alias explícito para NIVEL_CAMBIADO

# Residuos/Merma
WASTE_RECORDED          = "WASTE_RECORDED"      # Alias explícito para MERMA_CREATED con mejor semántica

# Cotizaciones
QUOTE_CONVERTED         = "QUOTE_CONVERTED"     # Nuevo: quote → sale conversion
                                                # payload: {quote_id, sale_id, customer_id}

QUOTE_EXPIRED           = "QUOTE_EXPIRED"       # Nuevo: quote expiration for follow-up
                                                # payload: {quote_id, customer_id, total, days_since_creation}


class EventBus:
    """Bus de eventos singleton thread-safe."""

    _instance:  Optional["EventBus"] = None
    _inst_lock: threading.Lock       = threading.Lock()

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            with cls._inst_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._handlers: Dict[str, List[Tuple[int, str, Handler]]] = {}
                    obj._lock     = threading.RLock()
                    obj._executor = ThreadPoolExecutor(
                        max_workers=4, thread_name_prefix="spj_event"
                    )
                    cls._instance = obj
        return cls._instance

    # ── API pública ───────────────────────────────────────────────────────────

    def subscribe(
        self,
        event_type: str,
        handler:    Handler,
        priority:   int = 0,
        label:      str = "",
    ) -> None:
        if not callable(handler):
            raise TypeError(f"handler debe ser callable, recibido: {type(handler)}")
        label = label or getattr(handler, "__qualname__", repr(handler))
        with self._lock:
            bucket = self._handlers.setdefault(event_type, [])
            for _, lbl, h in bucket:
                if h is handler:
                    logger.debug("Handler '%s' ya registrado para '%s'.", lbl, event_type)
                    return
            bucket.append((priority, label, handler))
            bucket.sort(key=lambda t: -t[0])
        logger.debug("Suscrito [%s] → %s (prio=%d)", event_type, label, priority)

    def unsubscribe(self, event_type: str, handler: Handler) -> bool:
        with self._lock:
            bucket = self._handlers.get(event_type, [])
            before = len(bucket)
            self._handlers[event_type] = [
                (p, l, h) for p, l, h in bucket if h is not handler
            ]
            return len(self._handlers[event_type]) < before

    def publish(
        self,
        event_type: str,
        payload:    dict,
        async_:     bool = False,
    ) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        if not handlers:
            logger.debug("Evento '%s' sin handlers registrados.", event_type)
            return

        if async_:
            self._executor.submit(self._dispatch, event_type, payload, handlers)
        else:
            self._dispatch(event_type, payload, handlers)

    def clear_handlers(self, event_type: Optional[str] = None) -> None:
        with self._lock:
            if event_type:
                self._handlers.pop(event_type, None)
            else:
                self._handlers.clear()

    def handler_count(self, event_type: str) -> int:
        with self._lock:
            return len(self._handlers.get(event_type, []))

    def registered_events(self) -> List[str]:
        with self._lock:
            return [e for e, hs in self._handlers.items() if hs]

    def _dispatch(
        self,
        event_type: str,
        payload:    dict,
        handlers:   List[Tuple[int, str, Handler]],
    ) -> None:
        for priority, label, handler in handlers:
            try:
                # Inject event_type into payload so handlers can identify the event
                enriched = dict(payload) if payload else {}
                if "event_type" not in enriched:
                    enriched["event_type"] = event_type
                handler(enriched)
                logger.debug("Handler OK: [%s] → %s", event_type, label)
            except Exception as exc:
                logger.error(
                    "Handler FALLÓ [%s] → %s: %s",
                    event_type, label, exc, exc_info=True,
                )


# ── Acceso global (singleton) ─────────────────────────────────────────────────
def get_bus() -> EventBus:
    """Retorna la instancia global del EventBus."""
    return EventBus()
