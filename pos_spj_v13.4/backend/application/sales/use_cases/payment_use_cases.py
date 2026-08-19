"""Payment use cases (POS-13/§30-36: Cash, Card, Transfer, Mixed, Credit,
Mercado Pago, Tests).

`RecordSalePaymentUseCase` is the one entry point for all five real payment
methods — "Mixed" is not a sixth method, it's what a sale becomes the
moment a second call records a different method than the first (see
`Sale.is_mixed_payment`), so this use case additionally requires
`SalesPermissions.PAYMENT_MIXED` on any call that would make that true.

`CompleteSaleUseCase` is the completion use case SALES-6's own docstring
explicitly deferred ("depends on real payment confirmation... doesn't exist
yet") — now buildable because `Sale.complete()` (POS-13) enforces
`SalePaymentPolicy.ensure_fully_paid` itself; this use case just persists
and emits the two reserved-but-previously-unused events
(`SaleEvents.PAYMENT_CONFIRMED`/`COMPLETED`).

Mercado Pago is intentionally NOT a hardware/webhook integration here.
Research for this phase confirmed a real, working MP integration already
exists on the LEGACY stack (`services/mercado_pago_service.py`: link
creation, webhook processing, `SalesService.confirm_pending_payment_sale`)
— rebuilding or relocating that is out of a payment-domain-modeling phase's
scope and would duplicate real, working code. What POS-13 gives the NEW
`Sale` aggregate is the ability to record an already-confirmed MP payment
as a line (method=MERCADO_PAGO, reference=the MP payment id) — the same
shape as Card/Transfer, no different plumbing.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.enums import PaymentMethod
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import CreditNotAuthorizedError, SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient

_PERMISSION_BY_METHOD = {
    PaymentMethod.CASH: SalesPermissions.PAYMENT_CASH,
    PaymentMethod.CARD: SalesPermissions.PAYMENT_CARD,
    PaymentMethod.TRANSFER: SalesPermissions.PAYMENT_TRANSFER,
    PaymentMethod.CREDIT: SalesPermissions.PAYMENT_CREDIT,
    PaymentMethod.MERCADO_PAGO: SalesPermissions.PAYMENT_MERCADO_PAGO,
}


class RecordSalePaymentUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, method: str, amount: Decimal,
        actor_user_id: str, operation_id: str, reference: str | None = None,
    ) -> SaleResult:
        try:
            payment_method = PaymentMethod(method)
        except ValueError:
            return SaleResult.fail(f"Método de pago desconocido: {method!r}", "VALIDATION",
                                   operation_id=operation_id)
        try:
            self._auth.require(actor_user_id, _PERMISSION_BY_METHOD[payment_method])
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            already_mixed_after = bool(sale.payments) and any(
                p.method != payment_method for p in sale.payments)
            if already_mixed_after:
                try:
                    self._auth.require(actor_user_id, SalesPermissions.PAYMENT_MIXED)
                except SalesDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=operation_id)

            if payment_method is PaymentMethod.CREDIT:
                if sale.customer_id is None:
                    return fail_from_domain_error(
                        CreditNotAuthorizedError(
                            "Una venta a crédito requiere un cliente asignado"),
                        operation_id=operation_id)
                approved, reason = SalesCreditClient(connection).validate(
                    customer_id=sale.customer_id, amount=amount)
                if not approved:
                    return fail_from_domain_error(
                        CreditNotAuthorizedError(reason), operation_id=operation_id)

            try:
                payment = sale.record_payment(
                    method=payment_method, amount=amount, captured_by_user_id=actor_user_id,
                    reference=reference)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            if payment_method is PaymentMethod.CREDIT:
                SalesCreditClient(connection).register(
                    customer_id=sale.customer_id, sale_id=sale.id,
                    folio=sale.sale_number or sale.id, amount=amount, branch_id=sale.branch_id)

            uow.sales.save(sale)
            self._emit(uow, SaleEvents.PAYMENT_RECORDED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, method=payment_method.value,
                       amount=str(payment.amount), payment_id=payment.id)
        return SaleResult.ok("Pago registrado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class CompleteSaleUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                sale.complete()
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.PAYMENT_CONFIRMED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id)
            self._emit(uow, SaleEvents.COMPLETED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       total=str(sale.totals.total))
        return SaleResult.ok("Venta completada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))
