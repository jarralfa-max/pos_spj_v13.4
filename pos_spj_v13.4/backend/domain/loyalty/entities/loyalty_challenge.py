"""LoyaltyChallenge — a goal-based gamification unit (master prompt §16).
Represents Retos/Misiones/Metas (``mode``) — see
``backend/domain/loyalty/enums.py::ChallengeMode`` for why the three master-
prompt classes collapse into one entity here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import ChallengeCriteriaType, ChallengeMode, ChallengeStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyChallengeStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _positive_decimal(value, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidLoyaltyChallengeStateError(f"{field_name} debe ser Decimal, nunca float")
    dec = Decimal(str(value))
    if dec <= 0:
        raise InvalidLoyaltyChallengeStateError(f"{field_name} debe ser positivo")
    return dec


@dataclass(slots=True)
class LoyaltyChallenge:
    id: str
    program_id: str
    code: str
    name: str
    criteria_type: ChallengeCriteriaType
    target_value: Decimal
    points_reward: Decimal
    mode: ChallengeMode = ChallengeMode.CHALLENGE
    description: str = ""
    status: ChallengeStatus = ChallengeStatus.DRAFT
    start_date: str | None = None
    end_date: str | None = None
    branch_scope: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.program_id:
            raise InvalidLoyaltyChallengeStateError("program_id es obligatorio")
        if not self.code or not self.code.strip():
            raise InvalidLoyaltyChallengeStateError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidLoyaltyChallengeStateError("name es obligatorio")
        self.target_value = _positive_decimal(self.target_value, "target_value")
        self.points_reward = _positive_decimal(self.points_reward, "points_reward")

    @classmethod
    def create(
        cls, program_id: str, code: str, name: str, criteria_type: ChallengeCriteriaType,
        target_value: Decimal, points_reward: Decimal, *, mode: ChallengeMode = ChallengeMode.CHALLENGE,
        description: str = "", start_date: str | None = None, end_date: str | None = None,
        branch_scope: str | None = None,
    ) -> "LoyaltyChallenge":
        return cls(
            id=new_uuid(), program_id=program_id, code=code.strip(), name=name.strip(),
            criteria_type=criteria_type, target_value=target_value, points_reward=points_reward,
            mode=mode, description=description, start_date=start_date, end_date=end_date,
            branch_scope=branch_scope,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        if self.status is not ChallengeStatus.DRAFT:
            raise InvalidLoyaltyChallengeStateError(
                f"No se puede activar desde {self.status.value}")
        self.status = ChallengeStatus.ACTIVE
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status not in (ChallengeStatus.DRAFT, ChallengeStatus.ACTIVE):
            raise InvalidLoyaltyChallengeStateError(
                f"No se puede cancelar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidLoyaltyChallengeStateError("La cancelación requiere un motivo")
        self.status = ChallengeStatus.CANCELLED
        self._touch()

    def expire(self) -> None:
        if self.status is not ChallengeStatus.ACTIVE:
            raise InvalidLoyaltyChallengeStateError(
                f"Solo expira un reto activo (actual: {self.status.value})")
        self.status = ChallengeStatus.EXPIRED
        self._touch()

    def is_active(self) -> bool:
        return self.status is ChallengeStatus.ACTIVE
