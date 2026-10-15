# erp/events.py — Integración con EventBus del ERP
"""
Emite y escucha eventos del ERP.
Cada evento incluye: sucursal_id, prioridad, timestamp.

CORRECCIÓN (FASE WA): WAEventEmitter usa ERP's bus.publish(), NO emit().
"""
from __future__ import annotations
from whatsapp_service.domain.money import dumps_decimal
import json
import logging
import os
from datetime import datetime
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger("wa.events")

# ── Eventos que EMITIMOS ──────────────────────────────────────────────────────
# Pedidos / ventas
WA_PEDIDO_CREADO        = "WA_PEDIDO_CREADO"
WA_COTIZACION_CREADA    = "WA_COTIZACION_CREADA"
WA_VENTA_CONFIRMADA     = "WA_VENTA_CONFIRMADA"
WA_ANTICIPO_REQUERIDO   = "WA_ANTICIPO_REQUERIDO"
WA_ANTICIPO_PAGADO      = "WA_ANTICIPO_PAGADO"
WA_ALERTA_GENERADA      = "WA_ALERTA_GENERADA"
WA_CLIENTE_REGISTRADO   = "WA_CLIENTE_REGISTRADO"

# ── Spec events (sección 6 del prompt) ───────────────────────────────────────
QUOTE_CREATED               = "QUOTE_CREATED"           # cotizacion_id, total, cliente_id
SALE_CREATED                = "SALE_CREATED"            # venta_id, folio, total, cliente_id
PAYMENT_REQUIRED            = "PAYMENT_REQUIRED"        # venta_id, monto, tipo
PAYMENT_RECEIVED            = "PAYMENT_RECEIVED"        # venta_id, monto, metodo, referencia
PURCHASE_ORDER_CREATED      = "PURCHASE_ORDER_CREATED"  # oc_id, producto_id, cantidad
DELIVERY_SCHEDULED          = "DELIVERY_SCHEDULED"      # venta_id, fecha, tipo_entrega
DELIVERY_CONFIRMED          = "DELIVERY_CONFIRMED"      # venta_id, folio
PAYMENT_REMINDER            = "PAYMENT_REMINDER"        # venta_id, folio, monto, phone
CLIENT_CONFIRMATION_REQUIRED= "CLIENT_CONFIRMATION_REQUIRED"  # venta_id, folio, phone
DELIVERY_REMINDER           = "DELIVERY_REMINDER"       # venta_id, folio, fecha, phone
PURCHASE_FOLLOWUP_REMINDER  = "PURCHASE_FOLLOWUP_REMINDER"    # oc_id, producto, phone
STAFF_NOTIFICATION          = "STAFF_NOTIFICATION"      # mensaje, tipo, sucursal_id
VACATION_REMINDER           = "VACATION_REMINDER"       # empleado_id, nombre, fecha_inicio
FORECAST_DEMAND_UPDATED     = "FORECAST_DEMAND_UPDATED" # producto_id, demanda_est, periodo
WHATSAPP_QUOTE_CREATED      = "WHATSAPP_QUOTE_CREATED"
WHATSAPP_QUOTE_ACCEPTED     = "WHATSAPP_QUOTE_ACCEPTED"
WHATSAPP_QUOTE_REJECTED     = "WHATSAPP_QUOTE_REJECTED"
WHATSAPP_QUOTE_CONVERTED_TO_SALE = "WHATSAPP_QUOTE_CONVERTED_TO_SALE"
WHATSAPP_MESSAGE_RECEIVED   = "WHATSAPP_MESSAGE_RECEIVED"
WHATSAPP_INTENT_DETECTED    = "WHATSAPP_INTENT_DETECTED"
WHATSAPP_ORDER_CONFIRMED_BY_CUSTOMER = "WHATSAPP_ORDER_CONFIRMED_BY_CUSTOMER"
WHATSAPP_QUOTE_ACCEPTED_BY_CUSTOMER = "WHATSAPP_QUOTE_ACCEPTED_BY_CUSTOMER"
WHATSAPP_NOTIFICATION_SENT  = "WHATSAPP_NOTIFICATION_SENT"
WHATSAPP_NOTIFICATION_FAILED = "WHATSAPP_NOTIFICATION_FAILED"
WHATSAPP_CONVERSATION_STATE_CHANGED = "WHATSAPP_CONVERSATION_STATE_CHANGED"

# ── Eventos que ESCUCHAMOS del ERP ────────────────────────────────────────────
ERP_STOCK_BAJO          = "STOCK_BAJO_MINIMO"
ERP_VENTA_COMPLETADA    = "VENTA_COMPLETADA"
ERP_AJUSTE_INVENTARIO   = "AJUSTE_INVENTARIO"
ERP_PAYROLL_DUE         = "PAYROLL_DUE"
ERP_EMPLOYEE_REST_DAY   = "EMPLOYEE_REST_DAY"
ERP_EMPLOYEE_OVERWORK   = "EMPLOYEE_OVERWORK"
ERP_FORECAST_GENERADO   = "FORECAST_GENERADO"


def _new_event_id() -> str:
    from backend.shared.ids import new_uuid
    return new_uuid()


class WAEventEmitter:
    """Durable channel event journal, readable from the ERP process.

    In-memory desktop buses cannot cross a process boundary. Persistence
    failures propagate, so a caller never mistakes a dropped event for success.
    """
    def __init__(self, db_conn=None):
        self.db = db_conn

    def emit(self, event_type: str, data: Dict[str, Any],
             sucursal_id: str | None = None, prioridad: int = 5):
        from backend.shared.ids import new_uuid
        if self.db is None:
            raise RuntimeError("A durable event connection is required")
        event_id = new_uuid()
        event_data = {**data, "event_id": event_id,
                      "operation_id": data.get("operation_id") or new_uuid(),
                      "sucursal_id": sucursal_id, "prioridad": prioridad,
                      "timestamp": datetime.now().isoformat(), "canal": "whatsapp"}
        self.db.execute(
            "INSERT INTO wa_event_log (id,event_type,data_json,sucursal_id,prioridad,timestamp) "
            "VALUES (?,?,?,?,?,?)",
            (event_id,event_type,dumps_decimal(event_data,ensure_ascii=False,default=str),
             sucursal_id,prioridad,event_data["timestamp"]))
        self.db.commit()
        logger.info("Channel event persisted: %s (%s)", event_type, event_id)

    def ensure_tables(self):
        """Validate the migration-owned journal without changing its schema."""
        if self.db is not None:
            self.db.execute("SELECT id,event_type,data_json FROM wa_event_log LIMIT 0")
