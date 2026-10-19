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

**ACTUALIZACIÓN 2026-10-15 (auditoría de Ventas V06, decisión del usuario
"todo o nada")**: `CashRegisterUnitOfWork` ya acepta `owns_transaction=False`,
así que este cliente corre DENTRO de la transacción de Ventas — si Caja
rechaza, la venta o la devolución no se registran. Lo que sigue es la
historia de por qué antes no se podía.

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
    # Vale o saldo a favor: instrumento comercial, no entra al cajón.
    PaymentMethod.VOUCHER: "REFUND_VOUCHER",
}


class SalesCashEffectsClient:
    def __init__(self) -> None:
        self._service = CashSalesIntegrationService()

    def require_open_shift(self, connection, *, branch_id: str, cashier_user_id: str) -> str:
        """El turno abierto del cajero en la sucursal, o `CashInvalidStateError`.

        Se consulta ANTES de completar la venta (Fase 6, decisión del usuario:
        exigir turno abierto). Antes sólo lo pedía el efecto de caja, que corre
        DESPUÉS del commit: la venta quedaba completada y el efectivo fuera de
        todo corte, con un aviso en el log y nada más."""
        return self._service.require_open_shift(
            connection, branch_id=branch_id, cashier_user_id=cashier_user_id)

    def record_completed_sale(
        self, connection, *, sale_id: str, branch_id: str, cashier_user_id: str,
        operation_id: str, payments: list, change: Decimal = Decimal("0"),
        owns_transaction: bool = False, sale_number: str | None = None,
    ) -> SaleCashResult:
        """`payments` is `Sale.payments` (a list of `SalePayment`) — grouped
        by method into the settlement-line shape Caja's service expects.
        Lines with the same method are summed (a sale can legitimately
        record two CASH lines, e.g. a correction)."""
        return self._service.record_completed_sale(
            connection, sale_id=sale_id, branch_id=branch_id, cashier_user_id=cashier_user_id,
            operation_id=operation_id, payment_lines=_payment_lines(payments),
            change=str(change), owns_transaction=owns_transaction, sale_number=sale_number)

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
            operation_id=operation_id, reason=reason, owns_transaction=False)

    def refund_returned_line(
        self, connection, refund_service, *, refund_id: str, sale_id: str, branch_id: str,
        actor_user_id: str, authorized_by: str, operation_id: str, payments: list,
        change: Decimal, refunds: list[tuple[str, Decimal]], reason: str,
    ):
        """El reembolso de una devolución parcial en Caja (decisión del
        usuario 2026-10-02: método original, efectivo primero).

        `refunds` es el reparto que decidió Ventas (`Sale.refund_plan`). Caja
        valida: turno abierto de quien devuelve, efectivo suficiente en el
        cajón, que no se reembolse más de lo cobrado por método, tope por
        operación, y que autorice OTRA persona. El crédito no pasa por Caja (no
        mueve dinero): baja la CxC en Finanzas con el evento de la devolución.
        """
        originales = _payment_lines(payments)
        for line in originales:
            if line["type"] == "CASH":
                line["amount"] = str(max(Decimal(line["amount"]) - Decimal(str(change)),
                                         Decimal("0")))
        # Ni el crédito ni el vale pasan por Caja: el crédito baja la CxC en
        # Finanzas y el vale recupera su saldo en Fidelidad, ambos con el evento
        # de la devolución. Antes el vale se mandaba a Caja sin su referencia y
        # Caja rechazaba TODA la devolución de una venta pagada con vale.
        pedidos = [{"type": _SETTLEMENT_TYPE_BY_METHOD[PaymentMethod(m)], "amount": str(a)}
                   for m, a in refunds
                   if PaymentMethod(m) not in (PaymentMethod.CREDIT, PaymentMethod.VOUCHER)]
        if not pedidos:
            return None
        return refund_service.process(
            connection, refund_id=refund_id, sale_id=sale_id, branch_id=branch_id,
            cashier_user_id=actor_user_id, authorized_by=authorized_by,
            operation_id=operation_id, original_payment_lines=originales,
            refund_lines=pedidos, reason=reason, owns_transaction=False)


def _payment_lines(payments) -> list[dict]:
    """Los pagos de la venta en la forma de Caja: uno por método, y el vale uno
    por instrumento CON su referencia — Caja exige identificar el instrumento
    (`REFUND_VOUCHER` requiere referencia validada). Medido 2026-10-15: sin ella
    Caja rechazaba la venta entera y el efectivo de un cobro vale+efectivo
    nunca llegaba al cajón (el error se tragaba después del commit)."""
    totals: dict[str, Decimal] = {}
    lines: list[dict] = []
    for payment in payments:
        settlement_type = _SETTLEMENT_TYPE_BY_METHOD[payment.method]
        if payment.method is PaymentMethod.VOUCHER:
            lines.append({"type": settlement_type, "amount": str(payment.amount),
                          "voucher_id": payment.reference or payment.id})
            continue
        totals[settlement_type] = totals.get(settlement_type, Decimal("0")) + payment.amount
    return [{"type": t, "amount": str(a)} for t, a in totals.items()] + lines

