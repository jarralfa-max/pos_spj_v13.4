"""ScheduleSupplierPaymentUseCase — programar NO toca saldos (§12).

Valida el contexto que debe seguir vigente también al ejecutar (proveedor en el
maestro, cuenta beneficiaria para pagos bancarios, tesorería de dinero real y
de la misma moneda, documento no bloqueado ni en disputa, saldo vigente) y fija
si el pago exigirá segunda autorización por su importe (configuración §28).
"""

from __future__ import annotations

from datetime import date

from backend.application.finance.ports import SupplierDirectoryPort
from backend.application.services.finance.posting_engine import publish_finance_event
from backend.application.use_cases.finance._support import (
    FORBIDDEN_SUPPLIER_PAYMENT_SOURCES,
    require_treasury,
)
from backend.domain.finance.entities.payable import Payable, SupplierPayment
from backend.domain.finance.enums import AuditAction, TreasuryAccountType
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    IdempotencyConflictError,
    PayableNotFoundError,
    PaymentAuthorizationError,
)
from backend.domain.finance.policies.segregation_policy import SegregationPolicy
from backend.domain.finance.services.payable_service import PayableService
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


def validate_payment_context(uow: FinanceUnitOfWork, directory: SupplierDirectoryPort, *,
                             payable: Payable, treasury_account_id: str, amount: Money):
    """Reglas que deben seguir siendo ciertas al programar Y al ejecutar."""
    payable.assert_payable()
    treasury = require_treasury(uow, treasury_account_id, currency_code=amount.currency_code,
                                money_only=False)
    forbidden = FORBIDDEN_SUPPLIER_PAYMENT_SOURCES.get(treasury.account_type)
    if forbidden:
        raise FinanceDomainError(forbidden)
    eligibility = directory.payment_eligibility(payable.supplier_id)
    if not eligibility.eligible:
        raise PaymentAuthorizationError(eligibility.reason)
    if treasury.account_type is TreasuryAccountType.BANK and not eligibility.bank_account:
        raise PaymentAuthorizationError(
            f"El proveedor {eligibility.name} no tiene cuenta bancaria registrada; "
            "un pago por banco necesita beneficiario")
    return treasury


class ScheduleSupplierPaymentUseCase:
    def __init__(self, supplier_directory: SupplierDirectoryPort) -> None:
        self._directory = supplier_directory

    def execute(self, connection, *, payable_id: str, amount: str, scheduled_date: date,
                treasury_account_id: str, scheduled_by: str, reference: str = "",
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.supplier_payments.find_by_operation_id(operation_id)
            if duplicate is not None:
                if duplicate.payable_id != payable_id:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya programó otro pago")
                return duplicate
            payable = uow.payables.get(payable_id)
            if payable is None:
                raise PayableNotFoundError("La cuenta por pagar no existe")
            money = Money.from_string(amount, payable.original_amount.currency_code)
            validate_payment_context(uow, self._directory, payable=payable,
                                     treasury_account_id=treasury_account_id, amount=money)
            in_flight = Money.zero(money.currency_code)
            for other in uow.supplier_payments.in_flight_amount(payable.id):
                in_flight = in_flight.add(other.amount)
            if in_flight.add(money) > payable.outstanding_amount:
                raise FinanceDomainError(
                    f"Con los pagos ya programados ({in_flight.to_string()}) se excede el "
                    f"saldo de la CxP ({payable.outstanding_amount.to_string()})")
            second = SegregationPolicy(uow.settings).requires_second_authorization(money)
            payment = PayableService().schedule_payment(
                payable, money, scheduled_date, treasury_account_id, operation_id,
                scheduled_by=scheduled_by, reference=reference,
                second_authorization_required=second)
            uow.supplier_payments.save(payment)
            uow.payables.update(payable)
            uow.audit(AuditAction.PAYMENT_SCHEDULED, entity_type="supplier_payment",
                      entity_id=payment.id, operation_id=operation_id, user_id=scheduled_by,
                      after={"payable_id": payable.id, "amount": money.to_string(),
                             "scheduled_date": scheduled_date.isoformat(),
                             "second_authorization_required": second},
                      branch_id=payable.branch_id)
            publish_finance_event(uow, EventName.SUPPLIER_PAYMENT_SCHEDULED, {
                "payment_id": payment.id, "payable_id": payable_id,
                "amount": money.to_string(), "second_authorization_required": second,
            }, operation_id=operation_id, entity_id=payment.id, branch_id=payable.branch_id)
            return payment
