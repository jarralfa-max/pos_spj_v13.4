"""SweepstakesWinner — one winning ticket selected in a draw (master prompt
§27). `(draw_id, ticket_id)` is unique at the schema level — the same
ticket can never win twice within the same draw."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.sweepstakes.enums import SweepstakesWinnerStatus
from backend.domain.sweepstakes.exceptions import (
    InvalidSweepstakesWinnerStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesWinner:
    id: str
    draw_id: str
    campaign_id: str
    ticket_id: str
    customer_id: str
    prize_id: str
    rank: int = 1
    status: SweepstakesWinnerStatus = SweepstakesWinnerStatus.PENDING_VALIDATION
    selected_at: str = field(default_factory=_utcnow)
    validated_at: str | None = None
    validated_by_user_id: str | None = None
    disqualification_reason: str | None = None
    delivered_at: str | None = None
    delivered_by_user_id: str | None = None

    def __post_init__(self) -> None:
        for attr in ("draw_id", "campaign_id", "ticket_id", "customer_id", "prize_id"):
            if not getattr(self, attr):
                raise InvalidSweepstakesWinnerStateError(f"{attr} es obligatorio")
        if self.rank <= 0:
            raise InvalidSweepstakesWinnerStateError("rank debe ser positivo")

    @classmethod
    def select(cls, draw_id: str, campaign_id: str, ticket_id: str, customer_id: str,
               prize_id: str, *, rank: int = 1) -> "SweepstakesWinner":
        return cls(id=new_uuid(), draw_id=draw_id, campaign_id=campaign_id, ticket_id=ticket_id,
                    customer_id=customer_id, prize_id=prize_id, rank=rank)

    def validate(self, validated_by_user_id: str) -> None:
        if self.status is not SweepstakesWinnerStatus.PENDING_VALIDATION:
            raise InvalidSweepstakesWinnerStateError(
                f"Solo se valida desde PENDING_VALIDATION (actual: {self.status.value})")
        self.status = SweepstakesWinnerStatus.VALIDATED
        self.validated_at = _utcnow()
        self.validated_by_user_id = validated_by_user_id

    def disqualify(self, reason: str) -> None:
        if self.status in (SweepstakesWinnerStatus.PRIZE_DELIVERED, SweepstakesWinnerStatus.DISQUALIFIED):
            raise InvalidSweepstakesWinnerStateError(
                f"No se puede descalificar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidSweepstakesWinnerStateError("La descalificación requiere un motivo")
        self.status = SweepstakesWinnerStatus.DISQUALIFIED
        self.disqualification_reason = reason

    def deliver_prize(self, delivered_by_user_id: str) -> None:
        if self.status is not SweepstakesWinnerStatus.VALIDATED:
            raise InvalidSweepstakesWinnerStateError(
                f"Solo se entrega desde VALIDATED (actual: {self.status.value})")
        self.status = SweepstakesWinnerStatus.PRIZE_DELIVERED
        self.delivered_at = _utcnow()
        self.delivered_by_user_id = delivered_by_user_id

    def expire(self) -> None:
        if self.status is not SweepstakesWinnerStatus.VALIDATED:
            raise InvalidSweepstakesWinnerStateError(
                f"Solo se expira desde VALIDATED (actual: {self.status.value})")
        self.status = SweepstakesWinnerStatus.EXPIRED
