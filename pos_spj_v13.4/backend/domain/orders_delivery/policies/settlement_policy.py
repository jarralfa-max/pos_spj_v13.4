"""SettlementPolicy (master prompt §46). Enum-transition-table style, mirrors
the rest of this domain's lifecycle policies.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import SettlementStatus
from backend.domain.orders_delivery.exceptions import InvalidSettlementStateError


class SettlementPolicy:
    TRANSITIONS = {
        (SettlementStatus.OPEN, SettlementStatus.BALANCED),
        (SettlementStatus.OPEN, SettlementStatus.WITH_DIFFERENCE),
        (SettlementStatus.WITH_DIFFERENCE, SettlementStatus.PENDING_REVIEW),
        (SettlementStatus.PENDING_REVIEW, SettlementStatus.APPROVED),
        (SettlementStatus.BALANCED, SettlementStatus.APPROVED),
        (SettlementStatus.APPROVED, SettlementStatus.POSTED),
        (SettlementStatus.POSTED, SettlementStatus.CLOSED),
    }
    FINAL_STATUSES = frozenset({SettlementStatus.CLOSED})

    @classmethod
    def ensure_transition(cls, *, current: SettlementStatus, target: SettlementStatus) -> None:
        if current in cls.FINAL_STATUSES:
            raise InvalidSettlementStateError("Final settlements cannot transition")
        if (current, target) not in cls.TRANSITIONS:
            raise InvalidSettlementStateError(
                f"Invalid settlement transition: {current.value} -> {target.value}")
