"""DriverSettlement (master prompt §46) — reconciles MANY
`DriverCashCollection`s for one driver: entregas asignadas/completadas,
efectivo esperado/entregado, diferencias. Auto-computes whether it is
BALANCED or WITH_DIFFERENCE at creation from what it's given — the caller
(a use case) is responsible for gathering the right collections, this
entity never queries anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import SettlementStatus
from backend.domain.orders_delivery.exceptions import SettlementRequiresCollectionsError
from backend.domain.orders_delivery.policies.settlement_policy import SettlementPolicy


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DriverSettlement:
    id: str
    driver_id: str
    branch_id: str
    collection_ids: tuple[str, ...]
    expected_total: Decimal
    collected_total: Decimal
    status: SettlementStatus = SettlementStatus.OPEN
    reviewed_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    closed_at: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def difference(self) -> Decimal:
        return self.collected_total - self.expected_total

    @classmethod
    def create(
        cls, *, driver_id: str, branch_id: str,
        collections: list,  # DriverCashCollection, avoiding an import cycle isn't needed but kept loose
    ) -> "DriverSettlement":
        validate_uuidv7(driver_id)
        validate_uuidv7(branch_id)
        if not collections:
            raise SettlementRequiresCollectionsError(
                "Una liquidación requiere al menos un cobro a conciliar")
        expected_total = sum((c.expected_amount for c in collections), Decimal("0"))
        collected_total = sum((c.collected_amount for c in collections), Decimal("0"))
        settlement = cls(
            id=new_uuid(), driver_id=driver_id, branch_id=branch_id,
            collection_ids=tuple(c.id for c in collections),
            expected_total=expected_total, collected_total=collected_total,
        )
        settlement._resolve_balance()
        return settlement

    def _resolve_balance(self) -> None:
        target = (SettlementStatus.BALANCED if self.difference == 0
                  else SettlementStatus.WITH_DIFFERENCE)
        SettlementPolicy.ensure_transition(current=self.status, target=target)
        self.status = target
        self.updated_at = _now()

    def submit_for_review(self, *, reviewed_by_user_id: str) -> None:
        validate_uuidv7(reviewed_by_user_id)
        SettlementPolicy.ensure_transition(
            current=self.status, target=SettlementStatus.PENDING_REVIEW)
        self.status = SettlementStatus.PENDING_REVIEW
        self.reviewed_by_user_id = reviewed_by_user_id
        self.updated_at = _now()

    def approve(self, *, approved_by_user_id: str) -> None:
        validate_uuidv7(approved_by_user_id)
        SettlementPolicy.ensure_transition(current=self.status, target=SettlementStatus.APPROVED)
        self.status = SettlementStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self.updated_at = _now()

    def post(self) -> None:
        SettlementPolicy.ensure_transition(current=self.status, target=SettlementStatus.POSTED)
        self.status = SettlementStatus.POSTED
        self.updated_at = _now()

    def close(self) -> None:
        SettlementPolicy.ensure_transition(current=self.status, target=SettlementStatus.CLOSED)
        self.status = SettlementStatus.CLOSED
        self.closed_at = _now()
        self.updated_at = _now()
