"""ReceivableService — domain rules for accounts receivable (§11)."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import (
    Collection,
    CollectionApplication,
    Receivable,
)
from backend.domain.finance.enums import ReceivableStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.policies.credit_policy import CreditPolicy, CustomerCreditProfile
from backend.domain.finance.value_objects.money import Money

AGING_BUCKETS = ("CURRENT", "1-30", "31-60", "61-90", "90+", "NO_DUE_DATE")


class ReceivableService:
    def __init__(self) -> None:
        self._credit_policy = CreditPolicy()

    def create_from_credit_sale(self, profile: CustomerCreditProfile | None,
                                financial_document_id: str, sale_total: Money,
                                issue_date: date, operation_id: str, *,
                                due_date: date | None = None,
                                branch_id: str | None = None) -> Receivable:
        self._credit_policy.enforce(profile, sale_total)
        assert profile is not None  # enforced above
        return Receivable.create(
            customer_id=profile.customer_id, financial_document_id=financial_document_id,
            amount=sale_total, issue_date=issue_date, operation_id=operation_id,
            due_date=due_date, branch_id=branch_id)

    @staticmethod
    def apply(collection: Collection, receivable: Receivable, amount: Money,
              operation_id: str, *, created_by: str | None = None) -> CollectionApplication:
        """Aplica parte de un cobro a una CxC: ambas reglas (≤ disponible del
        cobro, ≤ saldo de la CxC) se validan ANTES de mover cualquiera."""
        if collection.customer_id != receivable.customer_id:
            raise FinanceDomainError("El cobro y la cuenta por cobrar son de clientes distintos")
        if collection.amount.currency_code != receivable.outstanding_amount.currency_code:
            raise FinanceDomainError("El cobro y la cuenta por cobrar están en monedas distintas")
        if amount > collection.unapplied():
            collection.register_application(amount)  # lanza el error específico
        if not receivable.is_open:
            raise FinanceDomainError(f"No se aplica a una CxC {receivable.status.value}")
        receivable.apply_collection(amount)
        collection.register_application(amount)
        return CollectionApplication.create(collection.id, receivable.id, amount,
                                            operation_id, created_by=created_by)

    @staticmethod
    def aging_bucket(receivable: Receivable, as_of: date) -> str:
        if receivable.due_date is None:
            return "NO_DUE_DATE"
        days = receivable.days_overdue(as_of)
        if days == 0:
            return "CURRENT"
        if days <= 30:
            return "1-30"
        if days <= 60:
            return "31-60"
        if days <= 90:
            return "61-90"
        return "90+"

    @staticmethod
    def validate_customer_credit_note(amount: Money, receivable: Receivable) -> None:
        if amount > receivable.outstanding_amount:
            raise FinanceDomainError(
                "Una nota de crédito mayor que el saldo crea saldo a favor del cliente; "
                "regístrela como STORE_CREDIT")

    @staticmethod
    def is_collectible(receivable: Receivable) -> bool:
        return receivable.status not in (ReceivableStatus.CANCELLED,
                                         ReceivableStatus.WRITTEN_OFF,
                                         ReceivableStatus.COLLECTED)
