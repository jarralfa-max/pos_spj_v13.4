"""Referral — a customer referring another customer into a LoyaltyProgram
(master prompt §17). Bonus amounts/minimum purchase/deadline are explicit
constructor arguments, never literals in this file (§17: "No hardcodear
valores") — a future rules-configuration layer supplies them; this entity
only enforces the lifecycle and stores whatever it was given.

Self-referral (`SelfReferralNotAllowedError`) cannot be checked here — this
entity only knows `referred_customer_id`, not the referrer's own customer
identity (that requires resolving `referrer_membership_id` →
`loyalty_account_id` → `customer_id`, a repository lookup) — enforced in
`RegisterReferralUseCase` instead, which has that context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import ReferralStatus
from backend.domain.loyalty.exceptions import InvalidReferralStateError, ReferralNotQualifiedError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _non_negative_decimal(value, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidReferralStateError(f"{field_name} debe ser Decimal, nunca float")
    dec = Decimal(str(value))
    if dec < 0:
        raise InvalidReferralStateError(f"{field_name} no puede ser negativo")
    return dec


@dataclass(slots=True)
class Referral:
    id: str
    program_id: str
    referrer_membership_id: str
    referred_customer_id: str
    referrer_bonus_points: Decimal
    referred_bonus_points: Decimal = Decimal("0")
    minimum_purchase_amount: Decimal = Decimal("0")
    status: ReferralStatus = ReferralStatus.REGISTERED
    registered_at: str = field(default_factory=_utcnow)
    qualified_at: str | None = None
    rewarded_at: str | None = None
    closed_at: str | None = None
    closed_reason: str | None = None
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not self.program_id:
            raise InvalidReferralStateError("program_id es obligatorio")
        if not self.referrer_membership_id:
            raise InvalidReferralStateError("referrer_membership_id es obligatorio")
        if not self.referred_customer_id:
            raise InvalidReferralStateError("referred_customer_id es obligatorio")
        self.referrer_bonus_points = _non_negative_decimal(
            self.referrer_bonus_points, "referrer_bonus_points")
        self.referred_bonus_points = _non_negative_decimal(
            self.referred_bonus_points, "referred_bonus_points")
        self.minimum_purchase_amount = _non_negative_decimal(
            self.minimum_purchase_amount, "minimum_purchase_amount")

    @classmethod
    def register(
        cls, program_id: str, referrer_membership_id: str, referred_customer_id: str, *,
        referrer_bonus_points: Decimal, referred_bonus_points: Decimal = Decimal("0"),
        minimum_purchase_amount: Decimal = Decimal("0"), expires_at: str | None = None,
    ) -> "Referral":
        return cls(
            id=new_uuid(), program_id=program_id,
            referrer_membership_id=referrer_membership_id,
            referred_customer_id=referred_customer_id,
            referrer_bonus_points=referrer_bonus_points,
            referred_bonus_points=referred_bonus_points,
            minimum_purchase_amount=minimum_purchase_amount, expires_at=expires_at,
        )

    def qualify(self) -> None:
        if self.status is not ReferralStatus.REGISTERED:
            raise InvalidReferralStateError(
                f"Solo se califica un referido REGISTERED (actual: {self.status.value})")
        self.status = ReferralStatus.QUALIFIED
        self.qualified_at = _utcnow()

    def reward(self) -> None:
        if self.status is not ReferralStatus.QUALIFIED:
            raise ReferralNotQualifiedError(
                f"El referido debe estar QUALIFIED para recompensarse (actual: "
                f"{self.status.value})")
        self.status = ReferralStatus.REWARDED
        self.rewarded_at = _utcnow()

    def reject(self, reason: str) -> None:
        if self.status in (ReferralStatus.REWARDED, ReferralStatus.REJECTED):
            raise InvalidReferralStateError(
                f"No se puede rechazar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidReferralStateError("El rechazo requiere un motivo")
        self.status = ReferralStatus.REJECTED
        self.closed_at = _utcnow()
        self.closed_reason = reason

    def expire(self) -> None:
        if self.status not in (ReferralStatus.REGISTERED, ReferralStatus.QUALIFIED):
            raise InvalidReferralStateError(
                f"No se puede expirar desde {self.status.value}")
        self.status = ReferralStatus.EXPIRED
        self.closed_at = _utcnow()

    def flag_fraud_suspected(self, reason: str) -> None:
        if self.status is ReferralStatus.REWARDED:
            raise InvalidReferralStateError(
                "No se puede marcar como fraude un referido ya recompensado")
        if not (reason or "").strip():
            raise InvalidReferralStateError("La marca de fraude requiere un motivo")
        self.status = ReferralStatus.FRAUD_SUSPECTED
        self.closed_at = _utcnow()
        self.closed_reason = reason
