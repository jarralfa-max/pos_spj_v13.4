"""RewardRedemption — one customer's attempt to redeem a Reward (master
prompt §15's flow: Validar elegibilidad → Reservar puntos → ... → Confirmar
canje; en cancelación: Liberar reserva).

``points_transaction_id`` links to the RESERVE row LOY-6's ledger already
creates for the points hold — this entity does not duplicate the points
bookkeeping, only tracks the redemption's own lifecycle alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.enums import RewardRedemptionStatus
from backend.domain.loyalty.exceptions import (
    InvalidRewardRedemptionStateError,
    RewardNotAvailableError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class RewardRedemption:
    id: str
    reward_id: str
    membership_id: str
    loyalty_account_id: str
    points_transaction_id: str
    status: RewardRedemptionStatus = RewardRedemptionStatus.RESERVED
    sale_id: str | None = None
    requested_at: str = field(default_factory=_utcnow)
    confirmed_at: str | None = None
    cancelled_at: str | None = None

    def __post_init__(self) -> None:
        if not self.reward_id:
            raise RewardNotAvailableError("reward_id es obligatorio")
        if not self.membership_id:
            raise InvalidRewardRedemptionStateError("membership_id es obligatorio")
        if not self.points_transaction_id:
            raise InvalidRewardRedemptionStateError("points_transaction_id es obligatorio")

    @classmethod
    def request(
        cls, reward_id: str, membership_id: str, loyalty_account_id: str,
        points_transaction_id: str, *, sale_id: str | None = None,
    ) -> "RewardRedemption":
        return cls(id=new_uuid(), reward_id=reward_id, membership_id=membership_id,
                   loyalty_account_id=loyalty_account_id,
                   points_transaction_id=points_transaction_id, sale_id=sale_id)

    def confirm(self) -> None:
        if self.status is not RewardRedemptionStatus.RESERVED:
            raise InvalidRewardRedemptionStateError(
                f"Solo se confirma un canje RESERVED (actual: {self.status.value})")
        self.status = RewardRedemptionStatus.CONFIRMED
        self.confirmed_at = _utcnow()

    def cancel(self) -> None:
        if self.status is not RewardRedemptionStatus.RESERVED:
            raise InvalidRewardRedemptionStateError(
                f"Solo se cancela un canje RESERVED (actual: {self.status.value})")
        self.status = RewardRedemptionStatus.CANCELLED
        self.cancelled_at = _utcnow()
