"""CustomerCommercialEligibilityQuery (§49): "Ventas consume ...
CustomerCommercialEligibilityQuery... antes de completar una venta."

Pure customer-record eligibility — can this customer transact at all, at
the Customer Master level (status), independent of credit. Credit
eligibility is a separate, more sensitive query
(``backend.application.customer_credit.queries.
customer_credit_eligibility_query.CustomerCreditEligibilityQuery``) gated
by its own permission — a cash/card sale needs only this one.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customers.enums import CustomerStatus
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

_INELIGIBLE_STATUSES = {
    CustomerStatus.SUSPENDED: "El cliente está suspendido",
    CustomerStatus.BLOCKED: "El cliente está bloqueado",
    CustomerStatus.CLOSED: "El cliente está cerrado",
    CustomerStatus.MERGED: "El cliente fue fusionado con otro registro",
    CustomerStatus.ANONYMIZED: "El cliente fue anonimizado",
}


@dataclass(frozen=True)
class CommercialEligibilityResult:
    customer_id: str
    eligible: bool
    violations: tuple[str, ...]


class CustomerCommercialEligibilityQuery:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def check(self, customer_id: str, *, actor_user_id: str) -> CommercialEligibilityResult:
        self._auth.require(actor_user_id, CustomerPermissions.COMMERCIAL_ELIGIBILITY_CHECK)
        customer = self._uow.customers.get(customer_id)
        if customer is None:
            return CommercialEligibilityResult(
                customer_id=customer_id, eligible=False,
                violations=("El cliente no existe",))
        reason = _INELIGIBLE_STATUSES.get(customer.status)
        violations = (reason,) if reason else ()
        return CommercialEligibilityResult(
            customer_id=customer_id, eligible=not violations, violations=violations)
