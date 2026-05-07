# core/events/handlers/finance_handler.py — SPJ ERP v13.4  Phase 1 + Phase 6
"""
SaleFinanceHandler      — registers cash income when SALE_ITEMS_PROCESS fires (sync, inside SAVEPOINT).
SaleCreatedFinanceHandler — registers income journal entry when SALE_CREATED fires (post-transaction).

Phase 6: finance reacts to events only; direct finance mutations replaced by handlers.
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


class SaleCreatedFinanceHandler:
    """
    Subscribes to SALE_CREATED (= VENTA_COMPLETADA) post-transaction.
    Records the income journal entry via FinanceService.registrar_ingreso().

    Runs after the sale SAVEPOINT is committed, so it is not atomic with the
    sale row — this is intentional (post-commit downstream finance recording).
    Priority=50 in wiring (same slot as legacy venta_ledger inline lambda).

    Credit sales and zero-total sales are skipped.
    """

    def __init__(self, finance_service):
        self._finance = finance_service

    def handle(self, payload: Dict[str, Any]) -> None:
        total = float(payload.get("total", 0))
        if total <= 0:
            return
        if not hasattr(self._finance, "registrar_ingreso"):
            return
        try:
            self._finance.registrar_ingreso(
                concepto     = f"Venta #{payload.get('folio', payload.get('venta_id', ''))}",
                monto        = total,
                referencia_id= payload.get("venta_id"),
                usuario_id   = payload.get("usuario_id"),
                sucursal_id  = int(payload.get("sucursal_id", 1)),
                metadata     = {
                    "folio":      payload.get("folio"),
                    "cliente_id": payload.get("cliente_id"),
                },
            )
        except Exception as exc:
            logger.warning("SaleCreatedFinanceHandler: %s", exc)
