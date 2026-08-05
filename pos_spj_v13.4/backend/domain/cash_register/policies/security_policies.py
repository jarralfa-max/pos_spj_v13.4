"""Pure CASH-1 policies: monetary limits and segregation of duties."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum

from backend.domain.cash_register.exceptions import (
    CashLimitExceededError,
    CashSegregationOfDutiesError,
)


def _decimal(value: Decimal) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise TypeError("Cash Register limits require Decimal values")
    if not value.is_finite() or value < 0:
        raise ValueError("Cash Register limits require finite non-negative values")
    return value


class CashLimitDecision(str, Enum):
    WITHIN = "WITHIN"
    REQUIRES_AUTHORIZATION = "REQUIRES_AUTHORIZATION"
    EXCEEDS_HARD_CAP = "EXCEEDS_HARD_CAP"


class CashMonetaryLimitPolicy:
    def __init__(self, *, approval_threshold: Decimal, hard_cap: Decimal) -> None:
        self.approval_threshold = _decimal(approval_threshold)
        self.hard_cap = _decimal(hard_cap)
        if self.hard_cap < self.approval_threshold:
            raise ValueError("hard_cap cannot be below approval_threshold")

    def evaluate(self, amount: Decimal) -> CashLimitDecision:
        amount = _decimal(amount)
        if amount > self.hard_cap:
            return CashLimitDecision.EXCEEDS_HARD_CAP
        if amount > self.approval_threshold:
            return CashLimitDecision.REQUIRES_AUTHORIZATION
        return CashLimitDecision.WITHIN

    def require_operable(self, amount: Decimal) -> CashLimitDecision:
        decision = self.evaluate(amount)
        if decision is CashLimitDecision.EXCEEDS_HARD_CAP:
            raise CashLimitExceededError("El monto excede el límite máximo configurado")
        return decision


class CashSegregationOfDutiesPolicy:
    @staticmethod
    def _distinct(first: str, second: str, message: str) -> None:
        if not second or (first and first == second):
            raise CashSegregationOfDutiesError(message)

    def counter_cannot_review_own_difference(self, counter_id: str, reviewer_id: str) -> None:
        self._distinct(counter_id, reviewer_id,
                       "Quien contó no puede revisar su propia diferencia")

    def z_cut_creator_cannot_resolve_difference(self, creator_id: str, resolver_id: str) -> None:
        self._distinct(creator_id, resolver_id,
                       "Quien generó el Corte Z no puede resolver su diferencia")

    def handover_requires_distinct_parties(self, delivered_by: str, received_by: str) -> None:
        self._distinct(delivered_by, received_by,
                       "La entrega y recepción de valores requieren personas distintas")

    def refund_requester_requires_independent_authorizer(self, requested_by: str,
                                                          authorized_by: str) -> None:
        self._distinct(requested_by, authorized_by,
                       "El reembolso requiere un autorizador independiente")

    def reversal_requires_independent_authorizer(self, requested_by: str,
                                                  authorized_by: str) -> None:
        self._distinct(requested_by, authorized_by,
                       "El reverso requiere un autorizador independiente")

