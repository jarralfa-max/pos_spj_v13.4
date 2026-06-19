"""Delivery revenue recognition handler (defects 11, 14).

DeliveryRevenueFinanceHandler (on DELIVERY_TOTAL_FINALIZED)
  Books delivery revenue once per order into the GL (financial_event_log),
  idempotent by order_id. This shares the finalized cobrable total with
  Caja/Finanzas as revenue.

The driver-settlement cash reconciliation lives in the existing
DriverSettlementFinanceHandler (core/events/handlers/delivery_handler.py) — this
module intentionally does NOT duplicate that route.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.delivery_finance")


class DeliveryRevenueFinanceHandler:
    """Recognize delivery revenue in the GL when the total is finalized."""

    REVENUE_EVENT = "VENTA_DELIVERY"

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        order_id = payload.get("order_id")
        final_total = float(payload.get("final_total") or 0)
        if not order_id or final_total <= 0:
            return
        if self._already_posted(order_id):
            logger.info("delivery revenue already posted order=%s — skip", order_id)
            return

        branch_id = int(payload.get("branch_id") or 1)
        folio = payload.get("folio") or f"DEL-{order_id}"
        try:
            finance = self._finance_service()
            if finance is None:
                return
            finance.registrar_asiento(
                debe="105.1-caja-delivery",
                haber="401.0-ingresos-ventas",
                concepto=f"Ingreso delivery {folio}",
                monto=final_total,
                modulo="delivery",
                referencia_id=None,
                sucursal_id=branch_id,
                evento=self.REVENUE_EVENT,
                metadata={
                    "order_id": order_id,
                    "folio": folio,
                    "payment_method": payload.get("payment_method", ""),
                    "balance_due": payload.get("balance_due", 0),
                },
            )
            try:
                self.db.commit()
            except Exception:
                pass
            logger.info("delivery revenue posted order=%s total=%.2f", order_id, final_total)
        except Exception as exc:
            logger.error("DeliveryRevenueFinanceHandler order=%s: %s", order_id, exc)
            raise

    def _already_posted(self, order_id) -> bool:
        try:
            row = self.db.execute(
                "SELECT 1 FROM financial_event_log "
                "WHERE evento=? AND json_extract(metadata,'$.order_id')=? LIMIT 1",
                (self.REVENUE_EVENT, order_id),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _finance_service(self):
        try:
            from core.services.enterprise.finance_service import FinanceService
            return FinanceService(self.db)
        except Exception as exc:
            logger.debug("FinanceService unavailable: %s", exc)
            return None
