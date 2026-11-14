"""Payment use cases (POS-13/§30-36: Cash, Card, Transfer, Mixed, Credit,
Mercado Pago, Tests).

`RecordSalePaymentUseCase` is the one entry point for all five real payment
methods — "Mixed" is not a sixth method, it's what a sale becomes the
moment a second call records a different method than the first (see
`Sale.is_mixed_payment`), so this use case additionally requires
`SalesPermissions.PAYMENT_MIXED` on any call that would make that true.

`CompleteSaleUseCase` (completar sólo con el total, sin inventario, Caja ni
folio) se ELIMINÓ el 2026-10-15 (auditoría de Ventas V07): la única ruta para
completar una venta es `CheckoutSaleUseCase`, y
`tests/architecture/test_sales_single_completion_path.py` lo vigila.

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
from backend.domain.sales.exceptions import (
    CreditNotAuthorizedError,
    PaymentReferenceDuplicatedError,
    SalesDomainError,
    SaleNotFoundError,
)
from backend.domain.sales.policies.payment_policy import (
    REFERENCE_REQUIRED_METHODS,
    SalePaymentPolicy,
)
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient

_PERMISSION_BY_METHOD = {
    PaymentMethod.CASH: SalesPermissions.PAYMENT_CASH,
    PaymentMethod.CARD: SalesPermissions.PAYMENT_CARD,
    PaymentMethod.TRANSFER: SalesPermissions.PAYMENT_TRANSFER,
    PaymentMethod.CREDIT: SalesPermissions.PAYMENT_CREDIT,
    PaymentMethod.MERCADO_PAGO: SalesPermissions.PAYMENT_MERCADO_PAGO,
    PaymentMethod.VOUCHER: SalesPermissions.PAYMENT_VOUCHER,
}


def _ensure_processor_reference(repository: SaleRepository, *, method: PaymentMethod,
                                reference: str | None) -> None:
    """SDLC-PAY-002: obligatoria, con formato y sin otro pago vivo que la use.
    Un pago anulado o de una venta cancelada sale de `sale_payments`, así que
    su referencia queda libre."""
    SalePaymentPolicy.ensure_reference_valid(method=method, reference=reference)
    if method not in REFERENCE_REQUIRED_METHODS:
        return
    found = repository.find_live_payment_reference(method=method.value, reference=reference)
    if found is not None:
        raise PaymentReferenceDuplicatedError(
            f"La referencia {reference.strip()} ya está registrada en la venta {found}: un "
            "mismo pago no puede respaldar dos cobros.")


def payment_reference_problem(connection, *, method: str, reference: str | None,
                              taken: tuple = ()) -> str | None:
    """Por qué se rechazaría esta referencia, ANTES de iniciar el cobro.
    `taken`: pares (método, referencia) ya capturados y aún sin guardar."""
    try:
        payment_method = PaymentMethod(method)
        _ensure_processor_reference(SaleRepository(connection), method=payment_method,
                                    reference=reference)
    except ValueError:
        return None
    except SalesDomainError as exc:
        return str(exc)
    if payment_method in REFERENCE_REQUIRED_METHODS:
        key = reference.strip().upper()
        if any(m == method and (r or "").strip().upper() == key for m, r in taken):
            return "Esa referencia ya está en los pagos de este cobro."
    return None


class RecordSalePaymentUseCase(_SalesBaseUseCase):
    """Con método VOUCHER (2026-10-03) `reference` es el CÓDIGO del vale:
    Fidelidad valida vigencia, saldo y combinación (§24) y aparta el importe
    para esta venta; el pago guarda "TIPO:instancia" para que Finanzas lo
    liquide contra el pasivo del vale."""

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
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied

            try:
                _ensure_processor_reference(uow.sales, method=payment_method,
                                            reference=reference)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

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
                approved, reason = self._credit_client(connection, actor_user_id).validate(
                    customer_id=sale.customer_id, amount=amount)
                if not approved:
                    return fail_from_domain_error(
                        CreditNotAuthorizedError(reason), operation_id=operation_id)

            if payment_method is PaymentMethod.VOUCHER:
                from backend.infrastructure.integrations.sales_instruments_client import (
                    SalesInstrumentsClient,
                )
                vale = SalesInstrumentsClient(connection, actor_branch_id=sale.branch_id)                     .reserve_voucher(sale=sale, code=reference or "", amount=amount,
                                     actor_user_id=actor_user_id)
                if not vale["approved"]:
                    return SaleResult.fail(vale["reason"], "VOUCHER_REJECTED",
                                           operation_id=operation_id)
                amount = vale["amount"]
                reference = f"{vale['instrument_type']}:{vale['voucher_instance_id']}"

            try:
                payment = sale.record_payment(
                    method=payment_method, amount=amount, captured_by_user_id=actor_user_id,
                    reference=reference)
            except SalesDomainError as exc:
                if payment_method is PaymentMethod.VOUCHER:
                    # El pago no entró: el vale no queda apartado.
                    SalesInstrumentsClient(connection, actor_branch_id=sale.branch_id)                         .release_voucher(reservation_id=vale["reservation_id"],
                                         actor_user_id=actor_user_id)
                return fail_from_domain_error(exc, operation_id=operation_id)

            if payment_method is PaymentMethod.CREDIT:
                self._credit_client(connection, actor_user_id).register(
                    customer_id=sale.customer_id, sale_id=sale.id,
                    folio=sale.sale_number or sale.id, amount=amount, branch_id=sale.branch_id,
                    payment_id=payment.id)

            try:
                uow.sales.save(sale)
            except PaymentReferenceDuplicatedError as exc:
                # Otra caja guardó la misma referencia entre la revisión y aquí.
                uow.rollback()
                return fail_from_domain_error(exc, operation_id=operation_id)
            self._emit(uow, SaleEvents.PAYMENT_RECORDED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, method=payment_method.value,
                       amount=str(payment.amount), payment_id=payment.id)
        return SaleResult.ok("Pago registrado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))
