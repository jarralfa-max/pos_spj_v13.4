"""Credit policy — validates a credit sale against the customer credit profile."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.finance.exceptions import CreditPolicyViolationError
from backend.domain.finance.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class CustomerCreditProfile:
    """Snapshot of the customer credit configuration owned by the Customers module."""

    customer_id: str
    active: bool
    allows_credit: bool
    credit_limit: Money
    credit_balance: Money      # current outstanding debt


class CreditPolicy:
    def enforce(self, profile: CustomerCreditProfile | None, sale_total: Money) -> None:
        if profile is None or not profile.customer_id:
            raise CreditPolicyViolationError(
                "Para vender a crédito debe seleccionar un cliente con crédito autorizado."
            )
        if not profile.active:
            raise CreditPolicyViolationError("El cliente está inactivo.")
        if not profile.allows_credit:
            raise CreditPolicyViolationError("El cliente no tiene crédito autorizado.")
        if not profile.credit_limit.is_positive():
            raise CreditPolicyViolationError("El cliente no tiene límite de crédito configurado.")
        projected = profile.credit_balance.add(sale_total)
        if projected > profile.credit_limit:
            available = profile.credit_limit.subtract(profile.credit_balance)
            raise CreditPolicyViolationError(
                f"Crédito insuficiente: disponible ${available.to_string()}, "
                f"requerido ${sale_total.to_string()}."
            )
