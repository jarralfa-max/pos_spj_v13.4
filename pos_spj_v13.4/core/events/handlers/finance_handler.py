# core/events/handlers/finance_handler.py — SPJ ERP v13.5
"""Bridge adapters: legacy operational events → finance bounded context.

FASE 20 del refactor financiero: la ruta contable canónica ÚNICA es el
posting engine del bounded context (``backend/application/...finance``).
Estos adaptadores traducen los payloads del bus legacy (floats, claves en
español) al contrato canónico (cadenas decimales, UUIDs) y delegan en los
handlers nuevos. Aquí NO se deciden cuentas contables ni se escriben asientos.

Efectos operativos (CxC en cuentas_por_cobrar + credit_balance del cliente)
siguen siendo responsabilidad del módulo de clientes (CustomerCreditService);
el reconocimiento financiero vive exclusivamente en el ledger nuevo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.finance")


def _decimal_str(value: Any) -> str:
    """Normalize legacy float/str amounts to a canonical decimal string."""
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _occurred_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _settlements_from_legacy(payload: Dict[str, Any], net_total: str) -> list:
    """Map legacy payment_method/payment_breakdown to canonical settlements."""
    from core.services.payment_normalization import is_credit_sale

    payment_method = str(payload.get("payment_method") or payload.get("forma_pago") or "")
    normalized = payment_method.strip().lower()
    if is_credit_sale(payment_method):
        settlement_type = "ON_CREDIT"
    elif "tarjeta" in normalized or "card" in normalized:
        settlement_type = "CARD"
    elif "transfer" in normalized:
        settlement_type = "BANK_TRANSFER"
    else:
        settlement_type = "CASH"
    return [{"type": settlement_type, "amount": net_total}]


class SaleFinanceHandler:
    """SALE_ITEMS_PROCESS → SALE_COMPLETED canónico (síncrono, en SAVEPOINT)."""

    def __init__(self, db_conn=None, finance_service=None):  # finance_service: legacy kw, ignorado
        if db_conn is None:
            raise ValueError("SaleFinanceHandler requiere db_conn")
        from backend.application.event_handlers.finance.sale_completed_handler import (
            SaleCompletedHandler,
        )
        self._handler = SaleCompletedHandler(db_conn)

    def handle(self, payload: Dict[str, Any]) -> None:
        operation_id = str(payload.get("operation_id") or "").strip()
        sale_id = str(payload.get("sale_id") or payload.get("venta_id") or "").strip()
        total = _decimal_str(payload.get("total"))
        if not operation_id or not sale_id or float(total) <= 0:
            return
        canonical = {
            # evento puente: idempotencia por operación (el bus legacy no emite event_id)
            "event_id": f"bridge-sale-{operation_id}",
            "operation_id": operation_id,
            "sale_id": sale_id,
            "folio": str(payload.get("folio") or ""),
            "branch_id": str(payload.get("branch_id") or payload.get("sucursal_id") or "") or None,
            "customer_id": (str(payload.get("client_id") or payload.get("cliente_id")
                                or payload.get("customer_id") or "") or None),
            "occurred_at": _occurred_now(),
            "currency_code": "MXN",
            "gross_total": total,
            "discount_total": "0.00",
            "net_total": total,
            "tax_total": "0.00",
            "settlements": _settlements_from_legacy(payload, total),
        }
        self._handler.handle(canonical)


class CreditSaleFinanceHandler:
    """SALE_ITEMS_PROCESS (solo crédito) → CxC operativa del módulo de clientes.

    El asiento financiero de la venta a crédito lo publica SaleFinanceHandler
    (liquidación ON_CREDIT) en el ledger nuevo; aquí solo se mantiene el estado
    operativo de crédito (cuentas_por_cobrar + credit_balance), idempotente por
    venta_id.
    """

    def __init__(self, db_conn, finance_service=None):  # finance_service: legacy kw, ignorado
        self._db = db_conn

    def handle(self, payload: Dict[str, Any]) -> None:
        from core.services.payment_normalization import is_credit_sale

        payment_method = str(payload.get("payment_method", ""))
        if not is_credit_sale(payment_method):
            return
        total = float(payload.get("total", 0) or 0)
        cliente_id = str(payload.get("cliente_id") or payload.get("customer_id") or "")
        sale_id = str(payload.get("sale_id") or payload.get("venta_id") or "")
        sucursal_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
        if total <= 0 or not cliente_id or not sale_id:
            raise ValueError(
                "Venta a crédito sin cliente o venta válidos: "
                f"total={total:.2f} cliente_id={cliente_id!r} sale_id={sale_id!r}. "
                "La CxC no puede omitirse."
            )
        from application.services.customer_credit_service import CustomerCreditService
        CustomerCreditService(self._db).register_credit_sale(
            cliente_id=cliente_id,
            sale_id=sale_id,
            folio=str(payload.get("folio", "")),
            monto=total,
            sucursal_id=sucursal_id,
        )


class SaleCancelledFinanceHandler:
    """VENTA_CANCELADA → reverso espejo en el ledger nuevo + CxC operativa."""

    def __init__(self, db_conn, finance_service=None):  # finance_service: legacy kw, ignorado
        self._db = db_conn
        from backend.application.event_handlers.finance.sale_reversed_handler import (
            SaleReversedHandler,
        )
        self._handler = SaleReversedHandler(db_conn)

    def handle(self, payload: Dict[str, Any]) -> None:
        sale_id = str(payload.get("venta_id") or payload.get("sale_id") or "")
        operation_id = str(payload.get("operation_id") or "").strip() or f"cancel-{sale_id}"
        if not sale_id:
            return
        try:
            self._handler.handle({
                "event_id": f"bridge-sale-cancel-{sale_id}",
                "operation_id": operation_id,
                "sale_id": sale_id,
                "reason": str(payload.get("motivo") or "Venta cancelada"),
                "occurred_at": _occurred_now(),
            })
        except Exception as exc:
            # Post-commit: la venta ya quedó cancelada operativamente; se reporta
            # sin ocultar (queda en log y como excepción de integración en el
            # panel de instrumentos/eventos sin asiento).
            logger.error("SaleCancelledFinanceHandler: %s", exc)

        # Estado operativo de crédito (módulo clientes)
        from core.services.payment_normalization import is_credit_sale
        if is_credit_sale(str(payload.get("payment_method", payload.get("forma_pago", "")))):
            total = float(payload.get("total", 0) or 0)
            cliente_id = payload.get("cliente_id")
            self._db.execute(
                "UPDATE cuentas_por_cobrar SET estado='cancelada', saldo_pendiente=0"
                " WHERE venta_id=?",
                (sale_id,),
            )
            if cliente_id and total > 0:
                self._db.execute(
                    "UPDATE clientes SET"
                    " credit_balance = MAX(0, COALESCE(credit_balance,0) - ?),"
                    " saldo          = MAX(0, COALESCE(saldo,0) - ?)"
                    " WHERE id = ?",
                    (total, total, cliente_id),
                )


class PayrollFinanceHandler:
    """NOMINA_PAGADA → PAYROLL_PAID canónico (un asiento por pago).

    NOMINA_GENERADA ya no devenga aparte: el reconocimiento ocurre al pago,
    evitando el doble efecto del esquema legacy devengo+pago sin conciliación.
    """

    def __init__(self, db_conn=None, finance_service=None, journal_service=None):
        if db_conn is None:
            raise ValueError("PayrollFinanceHandler requiere db_conn")
        from backend.application.event_handlers.finance.payroll_paid_handler import (
            PayrollPaidHandler,
        )
        self._handler = PayrollPaidHandler(db_conn)

    def handle_generated(self, payload: Dict[str, Any]) -> None:
        logger.debug("NOMINA_GENERADA recibido; el reconocimiento ocurre al pago.")

    def handle_paid(self, payload: Dict[str, Any]) -> None:
        operation_id = str(payload.get("operation_id") or "").strip()
        if not operation_id:
            logger.warning("PayrollFinanceHandler NOMINA_PAGADA sin operation_id")
            return
        amount = _decimal_str(payload.get("neto", payload.get("total")))
        if float(amount) <= 0:
            return
        payroll_run_id = str(
            payload.get("payroll_payment_id") or payload.get("source_id")
            or payload.get("employee_id") or operation_id
        )
        self._handler.handle({
            "event_id": f"bridge-payroll-{operation_id}",
            "operation_id": operation_id,
            "payroll_run_id": payroll_run_id,
            "occurred_at": _occurred_now(),
            "currency_code": "MXN",
            "gross_salaries": amount,
            "social_security": "0.00",
            "net_paid": amount,
            "branch_id": str(payload.get("sucursal_id") or payload.get("branch_id") or "") or None,
        })
