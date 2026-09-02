"""SubstitutionPolicy (master prompt §28-29). "No sustituir silenciosamente"
— a substitution is never applied outright, only proposed; the customer (or
a supervisor via hot authorization, same pattern as catch-weight) must
resolve it before the line can be considered final.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import OrderLineStatus, SubstitutionType
from backend.domain.orders_delivery.exceptions import SubstitutionNotAllowedError


class SubstitutionPolicy:
    @staticmethod
    def ensure_can_propose(*, substitution_allowed: bool, status: OrderLineStatus) -> None:
        if not substitution_allowed:
            raise SubstitutionNotAllowedError(
                "Esta línea no permite sustituciones (substitution_allowed=False)")
        if status in (OrderLineStatus.SUBSTITUTED, OrderLineStatus.REJECTED,
                      OrderLineStatus.DELIVERED, OrderLineStatus.CANCELLED):
            raise SubstitutionNotAllowedError(
                f"No se puede proponer una sustitución para una línea en estado {status.value}")

    @staticmethod
    def ensure_valid_type(substitution_type: SubstitutionType) -> None:
        if substitution_type == SubstitutionType.NO_SUBSTITUTION:
            raise SubstitutionNotAllowedError(
                "NO_SUBSTITUTION no es un tipo de sustitución proponible")
