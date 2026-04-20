# core/services/analytics/analytics_engine.py — SPJ ERP
"""
AnalyticsEngine — Motor de Inteligencia de Negocios Reactivo.

Prioridad 5 = BI/analytics (la más baja per convenio).
Reacciona a eventos y agrega datos en tablas bi_*.
Non-fatal: nunca cancela la operación que originó el evento.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

logger = logging.getLogger("spj.analytics_engine")

_PRIORITY = 5


class AnalyticsEngine:
    """Suscriptor de eventos que alimenta las tablas BI de agregación."""

    def __init__(self, db_conn):
        self._db = db_conn
        self._subscribed = False

    def wire(self) -> None:
        """Registra handlers en el EventBus. Idempotente."""
        if self._subscribed:
            return
        from core.events.event_bus import get_bus
        from core.events.domain_events import SALE_CREATED, PRODUCTION_EXECUTED

        bus = get_bus()
        bus.subscribe(SALE_CREATED, self.update_sales,
                      priority=_PRIORITY, label="analytics.sales")
        bus.subscribe(PRODUCTION_EXECUTED, self.update_yield,
                      priority=_PRIORITY, label="analytics.yield")
        self._subscribed = True
        logger.info("AnalyticsEngine wired (prio=%d)", _PRIORITY)

    def update_sales(self, data: dict) -> None:
        """SALE_CREATED → UPSERT en bi_sales_daily."""
        try:
            fecha = (data.get("fecha") or datetime.now().strftime("%Y-%m-%d"))[:10]
            sucursal_id = int(data.get("sucursal_id", 1))
            total = float(data.get("total", 0))
            if total <= 0:
                return

            self._db.execute("""
                INSERT INTO bi_sales_daily
                    (fecha, sucursal_id, total_ventas, num_transacciones, promedio_ticket)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(fecha, sucursal_id) DO UPDATE SET
                    total_ventas      = total_ventas + excluded.total_ventas,
                    num_transacciones = num_transacciones + 1,
                    promedio_ticket   = (total_ventas + excluded.total_ventas)
                                        / (num_transacciones + 1)
            """, (fecha, sucursal_id, total, total))
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("update_sales non-fatal: %s", e)

    def update_yield(self, data: dict) -> None:
        """PRODUCTION_EXECUTED → INSERT en bi_transformations."""
        try:
            fecha = (data.get("fecha") or datetime.now().strftime("%Y-%m-%d"))[:10]
            sucursal_id = int(data.get("sucursal_id", 1))
            # Soporta payload plano y anidado via DomainEvent.to_dict()
            nested = (data.get("data") or {})
            rendimiento = float(
                data.get("rendimiento_pct")
                or nested.get("rendimiento_pct")
                or data.get("yield_pct")
                or 0
            )
            categoria = (
                data.get("categoria")
                or nested.get("categoria")
                or data.get("tipo", "")
            )
            inputs_json  = json.dumps(
                data.get("inputs") or nested.get("inputs") or data.get("insumos", []),
                ensure_ascii=False,
            )
            outputs_json = json.dumps(
                data.get("outputs") or nested.get("outputs") or data.get("productos", []),
                ensure_ascii=False,
            )

            self._db.execute("""
                INSERT INTO bi_transformations
                    (fecha, sucursal_id, categoria, inputs_json,
                     outputs_json, rendimiento_pct)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fecha, sucursal_id, categoria, inputs_json,
                  outputs_json, rendimiento))
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("update_yield non-fatal: %s", e)
