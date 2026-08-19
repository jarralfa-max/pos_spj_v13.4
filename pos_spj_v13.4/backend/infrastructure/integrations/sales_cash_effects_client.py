"""SalesCashEffectsClient — Sales' integration point onto Caja's real,
previously-unwired sale-settlement ledger (POS-14/§38-41: "Cash effects").

Research for SALES-13/SALES-14 confirmed `backend/application/cash_register/
sales_integration.py::CashSalesIntegrationService.record_completed_sale` is
real and complete — it requires an open Caja shift, classifies each
settlement line (cash/card/transfer/credit/Mercado Pago) via
`backend/domain/cash_register/settlements.py::classify_settlement`, and
writes a real `CashLedgerEntry` (`CASH_SALE`, INFLOW) for the cash-affecting
portion — but NO handler anywhere subscribes it to a Sales event, so it has
never actually run for a real sale.

**Not composed into the same atomic transaction as the sale's own
completion** — a real, load-bearing finding, not an oversight:
`CashRegisterUnitOfWork` (unlike `SalesUnitOfWork`/`InventoryUnitOfWork`)
has no `owns_transaction` flag — its `__exit__` always calls
`connection.commit()` directly. Calling `record_completed_sale` from inside
Sales' own open transaction would silently commit that transaction early,
breaking the atomicity `CheckoutSaleUseCase` exists to guarantee. This
client is therefore called by `CheckoutSaleUseCase` AFTER the sale's own
transaction has already committed — a deliberate best-effort, idempotent
side effect (the wrapped service already no-ops safely on retry via its own
`prior_payment` check), not something that can currently roll the sale back
if it fails. Fixing Cash Register's own UoW to support composition is a
Cash Register bounded-context change, out of this phase's scope.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.cash_register.ledger_use_cases import LedgerCommandResult
from backend.application.cash_register.sales_integration import CashSalesIntegrationService, SaleCashResult
from backend.domain.sales.enums import PaymentMethod

_SETTLEMENT_TYPE_BY_METHOD = {
    PaymentMethod.CASH: "CASH",
    PaymentMethod.CARD: "CARD",
    PaymentMethod.TRANSFER: "TRANSFER",
    PaymentMethod.CREDIT: "CUSTOMER_CREDIT",
    PaymentMethod.MERCADO_PAGO: "MERCADO_PAGO",
}


class SalesCashEffectsClient:
    def __init__(self) -> None:
        self._service = CashSalesIntegrationService()

    def record_completed_sale(
        self, connection, *, sale_id: str, branch_id: str, cashier_user_id: str,
        operation_id: str, payments: list, change: Decimal = Decimal("0"),
    ) -> SaleCashResult:
        """`payments` is `Sale.payments` (a list of `SalePayment`) — grouped
        by method into the settlement-line shape Caja's service expects.
        Lines with the same method are summed (a sale can legitimately
        record two CASH lines, e.g. a correction)."""
        totals: dict[str, Decimal] = {}
        for payment in payments:
            settlement_type = _SETTLEMENT_TYPE_BY_METHOD[payment.method]
            totals[settlement_type] = totals.get(settlement_type, Decimal("0")) + payment.amount
        payment_lines = [{"type": t, "amount": str(a)} for t, a in totals.items()]
        return self._service.record_completed_sale(
            connection, sale_id=sale_id, branch_id=branch_id, cashier_user_id=cashier_user_id,
            operation_id=operation_id, payment_lines=payment_lines, change=str(change))

    def reverse_completed_sale(
        self, connection, *, sale_id: str, branch_id: str, actor_user_id: str,
        operation_id: str, reason: str,
    ) -> LedgerCommandResult:
        """POS-16/§42-44: `CashSalesIntegrationService.reverse_sale_cash`
        (`cancel_sale` is a plain alias of the same method) writes a real
        `REVERSAL` `CashLedgerEntry` undoing the original `CASH_SALE`
        entry — a no-op if the sale never had a cash entry to begin with
        (`"Venta sin efectivo; no requiere compensación"`), and idempotent
        on retry (checks for a prior reversal first). Same best-effort,
        post-commit discipline as `record_completed_sale` — `Cash
        Register`'s own UoW still can't compose into Sales' transaction
        (see this module's own docstring)."""
        return self._service.reverse_sale_cash(
            connection, sale_id=sale_id, branch_id=branch_id, actor_user_id=actor_user_id,
            operation_id=operation_id, reason=reason)
