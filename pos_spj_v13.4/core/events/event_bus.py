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
# Producción
PRODUCCION_COMPLETADA   = "PRODUCCION_COMPLETADA"
PRODUCCION_INICIADA     = "PRODUCCION_INICIADA"
# Fidelidad
TARJETA_ESCANEADA       = "TARJETA_ESCANEADA"
PUNTOS_ACUMULADOS       = "PUNTOS_ACUMULADOS"
NIVEL_CAMBIADO          = "NIVEL_CAMBIADO"
# Fidelidad v13.4 (eventos auditables/idempotentes)
LOYALTY_POINTS_EARNED = "LOYALTY_POINTS_EARNED"
LOYALTY_POINTS_REDEEMED = "LOYALTY_POINTS_REDEEMED"
LOYALTY_POINTS_REVERSED = "LOYALTY_POINTS_REVERSED"
LOYALTY_POINTS_EXPIRED = "LOYALTY_POINTS_EXPIRED"
LOYALTY_CARD_ASSIGNED = "LOYALTY_CARD_ASSIGNED"
LOYALTY_CARD_BLOCKED = "LOYALTY_CARD_BLOCKED"
LOYALTY_REFERRAL_REWARDED = "LOYALTY_REFERRAL_REWARDED"
LOYALTY_BIRTHDAY_REWARD_ISSUED = "LOYALTY_BIRTHDAY_REWARD_ISSUED"
LOYALTY_FRAUD_BLOCKED = "LOYALTY_FRAUD_BLOCKED"
RAFFLE_CREATED = "RAFFLE_CREATED"
RAFFLE_BUDGET_RESERVED = "RAFFLE_BUDGET_RESERVED"
RAFFLE_ACTIVATED = "RAFFLE_ACTIVATED"
RAFFLE_TICKET_GRANTED = "RAFFLE_TICKET_GRANTED"
RAFFLE_TICKET_CANCELLED = "RAFFLE_TICKET_CANCELLED"
RAFFLE_CLOSED = "RAFFLE_CLOSED"
RAFFLE_WINNER_SELECTED = "RAFFLE_WINNER_SELECTED"
RAFFLE_PRIZE_DELIVERED = "RAFFLE_PRIZE_DELIVERED"
RAFFLE_BUDGET_RELEASED = "RAFFLE_BUDGET_RELEASED"

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

# Delivery extended — variable-weight & reservations (v13.5)
# payload shapes documented inline in DeliveryService
DELIVERY_ORDER_RESERVED       = "DELIVERY_ORDER_RESERVED"         # order_id, items[], branch_id, operation_id
DELIVERY_RESERVATION_RELEASED = "DELIVERY_RESERVATION_RELEASED"   # order_id, operation_id, released_count
DELIVERY_ITEM_WEIGHT_ADJUSTED = "DELIVERY_ITEM_WEIGHT_ADJUSTED"   # order_id, item_id, requested_qty, prepared_qty, new_total, cliente_tel, folio
DELIVERY_TOTAL_UPDATED        = "DELIVERY_TOTAL_UPDATED"          # order_id, old_total, new_total, folio, cliente_tel, cliente_email
DELIVERY_PAYMENT_UPDATED      = "DELIVERY_PAYMENT_UPDATED"        # order_id, payment_url, preference_id, new_total

# Delivery lifecycle — full flow state machine (v13.30)
DELIVERY_ORDER_CREATED        = "DELIVERY_ORDER_CREATED"          # order_id, folio, direccion, total, sucursal_id, usuario
DELIVERY_ORDER_CONFIRMED      = "DELIVERY_ORDER_CONFIRMED"        # order_id, folio, cliente_tel, total
DELIVERY_ORDER_PREPARING      = "DELIVERY_ORDER_PREPARING"        # order_id, folio, usuario
DELIVERY_DRIVER_ASSIGNED      = "DELIVERY_DRIVER_ASSIGNED"        # order_id, driver_id, driver_nombre, tiempo_estimado
DELIVERY_OUT_FOR_DELIVERY     = "DELIVERY_OUT_FOR_DELIVERY"       # order_id, driver_id, folio, cliente_tel
DELIVERY_ORDER_DELIVERED      = "DELIVERY_ORDER_DELIVERED"        # order_id, folio, driver_id, total, sucursal_id
DELIVERY_ORDER_CANCELLED      = "DELIVERY_ORDER_CANCELLED"        # order_id, folio, usuario, motivo
INVENTORY_COMMIT_REQUIRED     = "INVENTORY_COMMIT_REQUIRED"       # order_id, items[], sucursal_id, operation_id
INVENTORY_RELEASE_REQUIRED    = "INVENTORY_RELEASE_REQUIRED"      # order_id, operation_id, reason
CUSTOMER_NOTIFICATION_REQUESTED = "CUSTOMER_NOTIFICATION_REQUESTED"  # order_id, canal, template, params, cliente_tel
DRIVER_SETTLEMENT_CREATED     = "DRIVER_SETTLEMENT_CREATED"       # cut_id, driver_id, driver_nombre, efectivo, diferencia, fecha
PURCHASE_SUGGESTION_CREATED   = "PURCHASE_SUGGESTION_CREATED"     # producto_id, cantidad_sugerida, motivo, sucursal_id

# Caja (módulo de caja registradora)
CAJA_MOVIMIENTO           = "CAJA_MOVIMIENTO"
CAJA_TURNO_ABIERTO        = "CAJA_TURNO_ABIERTO"
CAJA_TURNO_CERRADO        = "CAJA_TURNO_CERRADO"
CAJA_CORTE_Z_GENERADO     = "CAJA_CORTE_Z_GENERADO"
CAJA_DIFERENCIA_DETECTADA = "CAJA_DIFERENCIA_DETECTADA"


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
        strict:     bool = False,
    ) -> None:
        """Publica un evento a todos los handlers registrados.

        strict=True — modo transaccional crítico:
            Si cualquier handler lanza una excepción, se relanza al llamador
            para que la transacción activa pueda hacer rollback.
            No debe usarse con async_=True.

        strict=False (default) — modo leniente:
            Los errores de handlers se loguean pero no se propagan.
            Comportamiento original — no rompe flujos no críticos.
        """
        if strict and async_:
            raise ValueError("publish(strict=True) no es compatible con async_=True")

        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        if not handlers:
            if strict:
                raise RuntimeError(f"Handlers críticos no registrados para evento '{event_type}'.")
            logger.debug("Evento '%s' sin handlers registrados.", event_type)
            return

        if async_:
            self._executor.submit(self._dispatch, event_type, payload, handlers, False)
        else:
            self._dispatch(event_type, payload, handlers, strict)

    def clear_handlers(self, event_type: Optional[str] = None) -> None:
        with self._lock:
            if event_type:
                self._handlers.pop(event_type, None)
            else:
                self._handlers.clear()

    def handler_count(self, event_type: str) -> int:
        with self._lock:
            return len(self._handlers.get(event_type, []))

    def handler_labels(self, event_type: str) -> List[str]:
        with self._lock:
            return [label for _, label, _ in self._handlers.get(event_type, [])]

    def registered_events(self) -> List[str]:
        with self._lock:
            return [e for e, hs in self._handlers.items() if hs]

    def _dispatch(
        self,
        event_type: str,
        payload:    dict,
        handlers:   List[Tuple[int, str, Handler]],
        strict:     bool = False,
    ) -> None:
        for priority, label, handler in handlers:
            try:
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
                if strict:
                    raise


# ── Acceso global (singleton) ─────────────────────────────────────────────────
def get_bus() -> EventBus:
    """Retorna la instancia global del EventBus."""
    return EventBus()
