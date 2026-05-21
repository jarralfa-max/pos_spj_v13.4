# core/events/handlers/finance_handler.py — SPJ ERP v13.4  Phase 1 + Phase 6
"""
SaleFinanceHandler      — registers cash income when SALE_ITEMS_PROCESS fires (sync, inside SAVEPOINT).
CreditSaleFinanceHandler — creates CxC + GL entry for credit sales (sync, inside SAVEPOINT, p=85).
SaleCancelledFinanceHandler — reverses CxC/income when VENTA_CANCELADA fires (post-commit).

Phase 6: finance reacts to events only; direct finance mutations replaced by handlers.

NOTE: SaleCreatedFinanceHandler was removed (2026-05-21 audit).
It was dead code — never subscribed in wiring.py — and would have caused double GL entries
if activated alongside SaleFinanceHandler (p=90). Removed per CLAUDE.md rule: eliminate
dead code detected in audit. See: docs/audits/FINANZAS_AUDIT_FIX_PLAN.md A-04.
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

        # Credit sales: income is deferred — CreditSaleFinanceHandler handles CxC.
        # MercadoPago: only a payment link is generated here — income registered
        # only after webhook confirmation. Do NOT record as collected income now.
        _DEFERRED = {"Credito", "Mercado Pago"}
        if payment_method in _DEFERRED or total <= 0:
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


class CreditSaleFinanceHandler:
    """
    Subscribes to SALE_ITEMS_PROCESS for credit sales only.

    Runs synchronously inside the sale SAVEPOINT (priority=85) so that both the
    CxC record and the GL journal entry are atomic with the sale row.

    Responsibilities:
    1. INSERT into cuentas_por_cobrar
    2. UPDATE clientes.credit_balance (increment debt)
    3. registrar_asiento: debe=130.1-cuentas-por-cobrar / haber=401.0-ingresos-ventas

    On any exception the handler re-raises so the SAVEPOINT rolls back the entire sale.
    Non-credit sales are ignored silently.
    """

    def __init__(self, db_conn, finance_service):
        self._db      = db_conn
        self._finance = finance_service

    def handle(self, payload: Dict[str, Any]) -> None:
        payment_method = str(payload.get("payment_method", ""))
        if payment_method != "Credito":
            return

        total       = float(payload.get("total", 0))
        cliente_id  = payload.get("cliente_id") or payload.get("customer_id")
        sale_id     = payload.get("sale_id") or payload.get("venta_id")
        folio       = str(payload.get("folio", ""))
        sucursal_id = int(payload.get("branch_id", payload.get("sucursal_id", 1)))

        if total <= 0 or not cliente_id or not sale_id:
            logger.warning(
                "CreditSaleFinanceHandler: incomplete payload "
                "total=%.2f cliente_id=%s sale_id=%s — skipping",
                total, cliente_id, sale_id,
            )
            return

        try:
            self._db.execute(
                """INSERT OR IGNORE INTO cuentas_por_cobrar
                       (cliente_id, venta_id, folio, monto_original,
                        saldo_pendiente, sucursal_id, estado)
                   VALUES (?, ?, ?, ?, ?, ?, 'pendiente')""",
                (cliente_id, sale_id, folio, total, total, sucursal_id),
            )
            # Sync both canonical columns — credit_balance (English service layer)
            # and saldo (Spanish legacy UI validation) must stay in lockstep.
            self._db.execute(
                "UPDATE clientes "
                "SET credit_balance = COALESCE(credit_balance, 0) + ?, "
                "    saldo          = COALESCE(saldo, 0) + ? "
                "WHERE id = ?",
                (total, total, cliente_id),
            )

            if hasattr(self._finance, "registrar_asiento"):
                self._finance.registrar_asiento(
                    debe         = "130.1-cuentas-por-cobrar",
                    haber        = "401.0-ingresos-ventas",
                    concepto     = f"Venta a crédito {folio}",
                    monto        = total,
                    modulo       = "ventas",
                    referencia_id= sale_id,
                    sucursal_id  = sucursal_id,
                    evento       = "VENTA_CREDITO",
                    metadata     = {"cliente_id": cliente_id, "folio": folio},
                )

            logger.info(
                "CreditSaleFinanceHandler: CxC registrada cliente=%s venta=%s folio=%s monto=%.2f",
                cliente_id, sale_id, folio, total,
            )
        except Exception as exc:
            logger.error("CreditSaleFinanceHandler.handle: %s", exc)
            raise  # re-raise: rolls back the SAVEPOINT


class SaleCancelledFinanceHandler:
    """
    Subscribes to VENTA_CANCELADA (post-commit, async) and posts the GL reversal entry.

    For cash sales: reverses the income journal (debe=401.0-ingresos-ventas / haber=110-caja).
    For credit sales: reverses CxC (debe=401.0-ingresos-ventas / haber=130.1-cuentas-por-cobrar)
                      and decrements credit_balance.

    Errors are logged but do NOT re-raise (post-commit, sale already recorded as cancelled).
    """

    def __init__(self, db_conn, finance_service):
        self._db      = db_conn
        self._finance = finance_service

    def handle(self, payload: Dict[str, Any]) -> None:
        total          = float(payload.get("total", 0))
        payment_method = str(payload.get("payment_method", payload.get("forma_pago", "")))
        folio          = str(payload.get("folio", ""))
        sale_id        = payload.get("venta_id") or payload.get("sale_id")
        sucursal_id    = int(payload.get("sucursal_id", payload.get("branch_id", 1)))
        cliente_id     = payload.get("cliente_id")

        if total <= 0 or not sale_id:
            return

        try:
            is_credit = payment_method == "Credito"

            if is_credit:
                # Reverse CxC: mark document as cancelled
                self._db.execute(
                    """UPDATE cuentas_por_cobrar
                          SET estado='cancelada', saldo_pendiente=0
                        WHERE venta_id=? AND sucursal_id=?""",
                    (sale_id, sucursal_id),
                )
                if cliente_id:
                    # Both columns must stay in lockstep (credit_balance=service layer, saldo=legacy UI)
                    self._db.execute(
                        "UPDATE clientes "
                        "SET credit_balance = MAX(0, COALESCE(credit_balance,0) - ?), "
                        "    saldo          = MAX(0, COALESCE(saldo,0) - ?) "
                        "WHERE id = ?",
                        (total, total, cliente_id),
                    )
                try:
                    self._db.commit()
                except Exception:
                    pass
                haber_cuenta = "130.1-cuentas-por-cobrar"
            else:
                haber_cuenta = "110-caja"

            if hasattr(self._finance, "registrar_asiento"):
                self._finance.registrar_asiento(
                    debe         = "401.0-ingresos-ventas",
                    haber        = haber_cuenta,
                    concepto     = f"Reversal cancelación venta {folio}",
                    monto        = total,
                    modulo       = "ventas",
                    referencia_id= sale_id,
                    sucursal_id  = sucursal_id,
                    evento       = "VENTA_CANCELADA",
                    metadata     = {
                        "folio":          folio,
                        "payment_method": payment_method,
                        "cliente_id":     cliente_id,
                    },
                )
            logger.info(
                "SaleCancelledFinanceHandler: reversal registrado venta=%s folio=%s total=%.2f",
                sale_id, folio, total,
            )
        except Exception as exc:
            logger.warning("SaleCancelledFinanceHandler.handle: %s", exc)
