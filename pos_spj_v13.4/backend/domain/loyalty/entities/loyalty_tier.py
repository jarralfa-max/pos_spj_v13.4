"""LoyaltyTier — a level/rank within a LoyaltyProgram (master prompt §14).

No hardcoded tier names/thresholds (§14, §9) — every field configured per
program, distinct from the legacy Growth Engine's own hardcoded
``nivel_bronce``/``nivel_plata``/``nivel_oro``/``nivel_platino`` columns
(LOY-0/LOY-3's own finding) this bounded context replaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import TierEvaluationMethod
from backend.domain.loyalty.exceptions import InvalidLoyaltyTierError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _non_negative_decimal(value, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidLoyaltyTierError(f"{field_name} debe ser Decimal, nunca float")
    dec = Decimal(str(value))
    if dec < 0:
        raise InvalidLoyaltyTierError(f"{field_name} no puede ser negativo")
    return dec


@dataclass(slots=True)
class LoyaltyTier:
    id: str
    program_id: str
    code: str
    name: str
    rank: int
    minimum_points: Decimal = Decimal("0")
    minimum_spend: Decimal = Decimal("0")
    minimum_visits: int = 0
    evaluation_method: TierEvaluationMethod = TierEvaluationMethod.LIFETIME
    evaluation_window_days: int | None = None
    benefit_multiplier: Decimal = Decimal("1")
    effective_from: str | None = None
    effective_to: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.program_id:
            raise InvalidLoyaltyTierError("program_id es obligatorio")
        if not self.code or not self.code.strip():
            raise InvalidLoyaltyTierError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidLoyaltyTierError("name es obligatorio")
        if self.rank < 0:
            raise InvalidLoyaltyTierError("rank no puede ser negativo")
        if self.minimum_visits < 0:
            raise InvalidLoyaltyTierError("minimum_visits no puede ser negativo")
        self.minimum_points = _non_negative_decimal(self.minimum_points, "minimum_points")
        self.minimum_spend = _non_negative_decimal(self.minimum_spend, "minimum_spend")
        self.benefit_multiplier = _non_negative_decimal(
            self.benefit_multiplier, "benefit_multiplier")

    @classmethod
    def create(
        cls, program_id: str, code: str, name: str, rank: int, *,
        minimum_points: Decimal = Decimal("0"), minimum_spend: Decimal = Decimal("0"),
        minimum_visits: int = 0, evaluation_method: TierEvaluationMethod = TierEvaluationMethod.LIFETIME,
        evaluation_window_days: int | None = None, benefit_multiplier: Decimal = Decimal("1"),
        effective_from: str | None = None, effective_to: str | None = None,
    ) -> "LoyaltyTier":
        return cls(
            id=new_uuid(), program_id=program_id, code=code.strip(), name=name.strip(),
            rank=rank, minimum_points=minimum_points, minimum_spend=minimum_spend,
            minimum_visits=minimum_visits, evaluation_method=evaluation_method,
            evaluation_window_days=evaluation_window_days,
            benefit_multiplier=benefit_multiplier, effective_from=effective_from,
            effective_to=effective_to,
        )

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _utcnow()

    def qualifies(self, *, lifetime_points: Decimal, total_spend: Decimal,
                  visit_count: int) -> bool:
        return (
            lifetime_points >= self.minimum_points
            and total_spend >= self.minimum_spend
            and visit_count >= self.minimum_visits
        )
