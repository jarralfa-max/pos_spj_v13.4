# erp/events.py — Integración con EventBus del ERP
"""
Emite y escucha eventos del ERP.
Cada evento incluye: sucursal_id, prioridad, timestamp.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger("wa.events")

# ── Eventos que EMITIMOS ──────────────────────────────────────────────────────
WA_PEDIDO_CREADO = "WA_PEDIDO_CREADO"
WA_COTIZACION_CREADA = "WA_COTIZACION_CREADA"
WA_VENTA_CONFIRMADA = "WA_VENTA_CONFIRMADA"
WA_ANTICIPO_REQUERIDO = "WA_ANTICIPO_REQUERIDO"
WA_ANTICIPO_PAGADO = "WA_ANTICIPO_PAGADO"
WA_ALERTA_GENERADA = "WA_ALERTA_GENERADA"
WA_CLIENTE_REGISTRADO = "WA_CLIENTE_REGISTRADO"

# ── Eventos que ESCUCHAMOS del ERP ────────────────────────────────────────────
ERP_STOCK_BAJO = "STOCK_BAJO"
ERP_VENTA_COMPLETADA = "VENTA_COMPLETADA"
ERP_AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"


class WAEventEmitter:
    """Emite eventos al EventBus del ERP."""

    def __init__(self, db_conn=None):
        self.db = db_conn
        self._bus = None
        self._init_bus()

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
        """Emite un evento con metadata estándar."""
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
                self.db.execute("""
                    INSERT INTO wa_event_log (event_type, data_json,
                        sucursal_id, prioridad, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (event_type, str(event_data)[:2000],
                      sucursal_id, prioridad))
                try:
                    self.db.commit()
                except Exception:
                    pass
            except Exception:
                pass  # Table may not exist yet

        # Emitir al EventBus del ERP
        if self._bus:
            try:
                self._bus.emit(event_type, event_data)
            except Exception as e:
                logger.debug("EventBus emit error: %s", e)

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
