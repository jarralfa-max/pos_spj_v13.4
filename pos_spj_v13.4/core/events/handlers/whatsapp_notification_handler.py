# core/events/handlers/whatsapp_notification_handler.py
"""
Manejador de eventos del EventBus para notificaciones WhatsApp.

REGLA CRÍTICA:
  El microservicio WhatsApp NO decide a quién notificar.
  Este handler aplica NotificationPolicyService antes de cualquier envío WA.

Eventos escuchados (definidos en wiring.py):
  - VENTA_COMPLETADA       → NO WA staff (solo cliente)
  - PEDIDO_WA_NUEVO        → NO WA staff (inbox only)
  - ANTICIPO_REGISTRADO    → NO WA staff (inbox only)
  - STOCK_BAJO             → NO WA staff (inbox only)
  - PEDIDO_ASIGNADO        → SÍ WA repartidor
  - NOMINA_PAGADA          → SÍ WA empleado
  - ALERTA_CRITICA         → SÍ WA responsables configurados

Prioridad: 10 (notificaciones — soft fail, no bloquea cadena)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("spj.handlers.wa_notification")


class WhatsAppNotificationHandler:
    """
    Intercepta eventos del bus y despacha a WA solo si la política lo permite.

    El handler NO envía directamente — delega a NotificationDispatcher
    que aplica política y escribe en inbox + WA según corresponda.
    """

    def __init__(self, db, whatsapp_svc=None, sucursal_id: int = 1) -> None:
        from core.services.notifications.notification_dispatcher import NotificationDispatcher
        from core.services.notifications.notification_policy_service import NotificationPolicyService
        from core.services.notifications.recipient_resolver import RecipientResolver

        self.db         = db
        self._dispatcher = NotificationDispatcher(db, whatsapp_svc, sucursal_id)
        self._resolver   = RecipientResolver(db)
        self._policy     = NotificationPolicyService()
        self.sucursal_id = sucursal_id

    # ── Handlers por tipo de evento ───────────────────────────────────────────

    def handle_pedido_wa_nuevo(self, payload: Dict[str, Any]) -> None:
        """Nuevo pedido WhatsApp → solo inbox ERP (NO WhatsApp al staff)."""
        folio      = payload.get("folio", "")
        cliente    = payload.get("cliente", "")
        total      = float(payload.get("total", 0))
        branch     = int(payload.get("sucursal_id") or self.sucursal_id)
        tipo       = "pedido_whatsapp_nuevo"
        titulo     = f"Nuevo pedido WA: {folio} — ${total:.2f}"
        empleados  = self._resolver.by_role(tipo, branch)

        # _policy.is_wa_allowed_for_staff("pedido_whatsapp_nuevo") → False
        # Dispatcher escribe solo en inbox
        self._dispatcher.dispatch_staff(
            tipo=tipo, destinatarios=empleados,
            titulo=titulo,
            mensaje="",   # vacío — WA no se enviará por política
            datos={"folio": folio, "cliente": cliente, "total": total},
            sucursal_id=branch,
        )

    def handle_anticipo(self, payload: Dict[str, Any]) -> None:
        """Anticipo requerido/recibido → solo inbox ERP."""
        tipo   = payload.get("subtipo", "anticipo_requerido")
        folio  = payload.get("folio", "")
        monto  = float(payload.get("monto", 0))
        branch = int(payload.get("sucursal_id") or self.sucursal_id)
        empleados = self._resolver.by_role("venta_cancelada", branch)  # gerente+admin
        self._dispatcher.dispatch_staff(
            tipo=tipo, destinatarios=empleados,
            titulo=f"Anticipo {folio}: ${monto:.2f}",
            mensaje="",
            datos={"folio": folio, "monto": monto},
            sucursal_id=branch,
        )

    def handle_pedido_asignado(self, payload: Dict[str, Any]) -> None:
        """Pedido asignado al repartidor → SÍ WA (política permite)."""
        repartidor_id = payload.get("repartidor_id") or payload.get("empleado_id")
        folio         = payload.get("folio", "")
        direccion     = payload.get("direccion", "")
        branch        = int(payload.get("sucursal_id") or self.sucursal_id)
        if not repartidor_id:
            return
        emp = self._resolver.by_employee_id(int(repartidor_id))
        if not emp:
            return
        telefono = (emp.get("telefono") or "").strip()
        nombre   = emp.get("nombre", "repartidor")
        mensaje  = (
            f"🛵 *Pedido asignado*\n"
            f"Folio: {folio}\n"
            f"Dirección: {direccion}\n"
            f"¡Buen viaje, {nombre.split()[0]}!"
        )
        self._dispatcher.dispatch_driver(
            empleado_id=int(repartidor_id),
            telefono=telefono,
            mensaje=mensaje,
            datos={"folio": folio, "direccion": direccion},
            sucursal_id=branch,
        )

    def handle_alerta_critica(self, payload: Dict[str, Any]) -> None:
        """
        Alerta crítica (diferencia_caja, backup_fallido, alerta_seguridad, etc.).
        Solo envía WA a responsables EXPLÍCITAMENTE configurados en DB.
        Tipo canónico: payload["tipo"] → debe estar en WA_STAFF_ALLOWED.
        """
        tipo    = payload.get("tipo", "alerta_operacion_critica")
        titulo  = payload.get("titulo", "Alerta crítica")
        mensaje = payload.get("mensaje", "")
        datos   = payload.get("datos", {})
        branch  = int(payload.get("sucursal_id") or self.sucursal_id)

        if not self._policy.is_wa_allowed_for_staff(tipo):
            logger.debug("handle_alerta_critica: tipo=%s bloqueado por política", tipo)
            return

        # Responsables explícitamente configurados para este tipo
        responsibles = self._resolver.explicit_responsibles(tipo, branch)
        # Fallback: roles por defecto del tipo
        if not responsibles:
            responsibles = self._resolver.by_role(tipo, branch)

        self._dispatcher.dispatch_staff(
            tipo=tipo, destinatarios=responsibles,
            titulo=titulo, mensaje=mensaje, datos=datos,
            sucursal_id=branch,
        )

    def handle_forecast(self, payload: Dict[str, Any]) -> None:
        """Sugerencia de compra → WA a gerentes/compras configurados."""
        tipo    = "forecast_sugerencia_compra"
        titulo  = payload.get("titulo", "Sugerencia de compra")
        mensaje = payload.get("mensaje", titulo)
        datos   = payload.get("datos", {})
        branch  = int(payload.get("sucursal_id") or self.sucursal_id)
        responsibles = self._resolver.by_role(tipo, branch)
        self._dispatcher.dispatch_staff(
            tipo=tipo, destinatarios=responsibles,
            titulo=titulo, mensaje=mensaje, datos=datos,
            sucursal_id=branch,
        )

    def handle(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Punto de entrada genérico para el EventBus.
        Despacha al método correcto según event_type.
        """
        try:
            _MAP = {
                "PEDIDO_WA_NUEVO":     self.handle_pedido_wa_nuevo,
                "ANTICIPO_REGISTRADO": self.handle_anticipo,
                "ANTICIPO_REQUERIDO":  self.handle_anticipo,
                "PEDIDO_ASIGNADO":     self.handle_pedido_asignado,
                "ALERTA_CRITICA":      self.handle_alerta_critica,
                "FORECAST_SUGERENCIA": self.handle_forecast,
            }
            fn = _MAP.get(event_type)
            if fn:
                fn(payload)
            else:
                logger.debug("wa_notification_handler: evento no mapeado: %s", event_type)
        except Exception as exc:
            logger.warning(
                "wa_notification_handler.handle(%s): %s", event_type, exc, exc_info=True)
