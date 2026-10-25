"""AuthorizeSupplierPaymentUseCase — autorización separada de programar y ejecutar (§12, §28).

Quien programa no autoriza. Sobre el umbral configurado el pago exige una
segunda autorización de OTRA persona; sólo con todas queda AUTORIZADO.
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.payable import SupplierPayment
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError, PayableNotFoundError
from backend.domain.finance.policies.segregation_policy import SegregationPolicy
from backend.domain.finance.services.payable_service import PayableService
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class AuthorizeSupplierPaymentUseCase:
    def execute(self, connection, *, payment_id: str, authorized_by: str,
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            payable = uow.payables.get(payment.payable_id)
            if payable is None:
                raise PayableNotFoundError("La CxP del pago no existe")
            SegregationPolicy(uow.settings).enforce_payment_authorization(
                scheduled_by=payment.scheduled_by, authorizer=authorized_by,
                first_authorizer=payment.authorized_by)
            before = {"status": payment.status.value, "authorized_by": payment.authorized_by}
            fully = PayableService().authorize_payment(payment, payable, authorized_by)
            uow.supplier_payments.update(payment)
            uow.payables.update(payable)
            uow.audit(AuditAction.PAYMENT_AUTHORIZED, entity_type="supplier_payment",
                      entity_id=payment.id, operation_id=operation_id, user_id=authorized_by,
                      before=before,
                      after={"status": payment.status.value, "fully_authorized": fully,
                             "second_authorized_by": payment.second_authorized_by},
                      branch_id=payment.branch_id)
            publish_finance_event(uow, EventName.SUPPLIER_PAYMENT_AUTHORIZED, {
                "payment_id": payment.id, "authorized_by": authorized_by,
                "fully_authorized": fully,
            }, operation_id=operation_id, entity_id=payment.id, branch_id=payment.branch_id)
            return payment
