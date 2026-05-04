# core/events/handlers/finance_handler.py — SPJ ERP v13.4  Phase 1
"""
SaleFinanceHandler — registers cash income when SALE_ITEMS_PROCESS is received.

Extracted from sales_service.py (Phase 1 decoupling).
Registered by wiring.py at priority=90 (sync, inside SAVEPOINT).

Credit sales are skipped here; their accounting entry is handled by
CustomerCreditService.register_credit_sale() post-commit.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.finance")


class SaleFinanceHandler:
    """
    Subscribes to SALE_ITEMS_PROCESS and registers the cash income via FinanceService.

    Args:
        finance_service: Must implement register_income(...).
    """

    def __init__(self, finance_service):
        self._finance = finance_service

    def handle(self, payload: Dict[str, Any]) -> None:
        payment_method = str(payload.get("payment_method", "Efectivo"))
        total          = float(payload.get("total", 0))

        # Credit sales: income is deferred — CustomerCreditService handles CxC post-commit.
        if payment_method == "Credito" or total <= 0:
            return

        try:
            self._finance.register_income(
                amount        = total,
                category      = "VENTAS_MOSTRADOR",
                description   = f"Ingreso por venta {payload.get('folio', '')}",
                payment_method= payment_method,
                branch_id     = int(payload.get("branch_id", payload.get("sucursal_id", 1))),
                user          = str(payload.get("user", payload.get("usuario", "sistema"))),
                operation_id  = str(payload.get("operation_id", "")),
                reference_id  = payload.get("sale_id", payload.get("venta_id")),
            )
        except Exception as exc:
            logger.error("SaleFinanceHandler.handle: %s", exc)
            raise  # re-raise so wiring can log the failure
