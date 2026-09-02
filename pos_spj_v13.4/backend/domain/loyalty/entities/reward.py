"""Reward — a redeemable benefit definition within a LoyaltyProgram (master
prompt §15). ``value`` is interpreted per ``reward_type`` (discount amount,
percentage, fixed amount, etc.) at the application layer that actually
applies the benefit — this entity only stores the configured number,
consistent with §9's "no hardcodear... bonos" rule applied at this layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import RewardType
from backend.domain.loyalty.exceptions import InvalidRewardError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Reward:
    id: str
    program_id: str
    code: str
    name: str
    reward_type: RewardType
    points_cost: Decimal
    description: str = ""
    value: Decimal = Decimal("0")
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.program_id:
            raise InvalidRewardError("program_id es obligatorio")
        if not self.code or not self.code.strip():
            raise InvalidRewardError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidRewardError("name es obligatorio")
        if isinstance(self.points_cost, bool) or isinstance(self.points_cost, float):
            raise InvalidRewardError("points_cost debe ser Decimal, nunca float")
        self.points_cost = Decimal(str(self.points_cost))
        if self.points_cost <= 0:
            raise InvalidRewardError("points_cost debe ser positivo")
        if isinstance(self.value, bool) or isinstance(self.value, float):
            raise InvalidRewardError("value debe ser Decimal, nunca float")
        self.value = Decimal(str(self.value))

    @classmethod
    def create(
        cls, program_id: str, code: str, name: str, reward_type: RewardType,
        points_cost: Decimal, *, description: str = "", value: Decimal = Decimal("0"),
    ) -> "Reward":
        return cls(id=new_uuid(), program_id=program_id, code=code.strip(),
                   name=name.strip(), reward_type=reward_type, points_cost=points_cost,
                   description=description, value=value)

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _utcnow()
