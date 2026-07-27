# erp/events.py — Integración con EventBus del ERP
"""
Emite y escucha eventos del ERP.
Cada evento incluye: sucursal_id, prioridad, timestamp.

CORRECCIÓN (FASE WA): WAEventEmitter usa ERP's bus.publish(), NO emit().
"""
from __future__ import annotations
import json
import logging
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


class WAEventEmitter:
    """Emite eventos al EventBus del ERP."""

    def __init__(self, db_conn=None):
        self.db = db_conn
        self._bus = None
        self._init_bus()
        if db_conn:
            self.ensure_tables()

    def _init_bus(self):
        try:
            import sys, os
            # Agregar ruta del ERP al path si no está
            erp_path = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            erp_module = os.path.join(erp_path, "pos_spj_v13.4")
            if os.path.exists(erp_module) and erp_module not in sys.path:
                sys.path.insert(0, erp_module)

            from core.events.event_bus import get_bus
            self._bus = get_bus()
            logger.info("EventBus del ERP conectado")
        except ImportError:
            logger.warning("EventBus no disponible — eventos solo se logean")

    def emit(self, event_type: str, data: Dict[str, Any],
             sucursal_id: int = 1, prioridad: int = 5):
        """
        Emite un evento con metadata estándar.

        FIX: ERP EventBus usa publish(), no emit().
        Usa async_=True para eventos no-críticos que no deben bloquear el flujo WA.
        """
        event_data = {
            **data,
            "sucursal_id": sucursal_id,
            "prioridad": prioridad,
            "timestamp": datetime.now().isoformat(),
            "canal": "whatsapp",
        }

        # Log siempre
        logger.info("EVENT %s: %s (suc=%d, pri=%d)",
                     event_type, str(data)[:100], sucursal_id, prioridad)

        # Guardar en BD para trazabilidad
        if self.db:
            try:
                # Serialize payload as real JSON (not str())
                try:
                    data_json = json.dumps(event_data, ensure_ascii=False,
                                           default=str)[:4000]
                except Exception:
                    data_json = str(event_data)[:4000]
                self.db.execute("""
                    INSERT INTO wa_event_log (event_type, data_json,
                        sucursal_id, prioridad, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (event_type, data_json, sucursal_id, prioridad))
                try:
                    self.db.commit()
                except Exception:
                    pass
            except Exception:
                pass  # Table may not exist yet

        # Emitir al EventBus del ERP (usa publish(), no emit())
        # Prioridad ≥ 80 → crítico (síncrono); resto async para no bloquear WA.
        # Ref: CLAUDE.md priority table: 80 = operaciones críticas de negocio.
        if self._bus:
            try:
                is_critical = prioridad >= 80
                self._bus.publish(event_type, event_data, async_=not is_critical)
            except Exception as e:
                logger.debug("EventBus publish error: %s", e)

    def ensure_tables(self):
        if self.db:
            try:
                self.db.execute("""
                    CREATE TABLE IF NOT EXISTS wa_event_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        data_json TEXT,
                        sucursal_id INTEGER DEFAULT 1,
                        prioridad INTEGER DEFAULT 5,
                        timestamp TEXT DEFAULT (datetime('now'))
                    )
                """)
                try:
                    self.db.commit()
                except Exception:
                    pass
            except Exception:
                pass
