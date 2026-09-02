"""SweepstakesDraw — one draw ceremony for a campaign (master prompt §27).

`random_seed`/`pool_hash` mirror the legacy `raffle_winners` table's own
anti-fraud fields (`migrations/standalone/113_raffle_subsystem.py`) — kept
deliberately, since that design was already sound: a draw records the seed
that produced it and a hash of the exact eligible-ticket pool it drew from,
so the result can be independently re-verified later."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.sweepstakes.enums import SweepstakesDrawStatus
from backend.domain.sweepstakes.exceptions import (
    EmptyTicketPoolError,
    InvalidSweepstakesDrawStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesDraw:
    id: str
    campaign_id: str
    status: SweepstakesDrawStatus = SweepstakesDrawStatus.SCHEDULED
    scheduled_at: str | None = None
    executed_at: str | None = None
    executed_by_user_id: str | None = None
    random_seed: str | None = None
    pool_hash: str | None = None
    ticket_pool_size: int = 0
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise InvalidSweepstakesDrawStateError("campaign_id es obligatorio")

    @classmethod
    def schedule(cls, campaign_id: str, *, scheduled_at: str | None = None) -> "SweepstakesDraw":
        return cls(id=new_uuid(), campaign_id=campaign_id, scheduled_at=scheduled_at)

    def complete(self, *, executed_by_user_id: str, random_seed: str, pool_hash: str,
                 ticket_pool_size: int) -> None:
        if self.status is not SweepstakesDrawStatus.SCHEDULED:
            raise InvalidSweepstakesDrawStateError(
                f"Solo se completa desde SCHEDULED (actual: {self.status.value})")
        if ticket_pool_size <= 0:
            raise EmptyTicketPoolError("No hay boletos elegibles para este sorteo")
        self.status = SweepstakesDrawStatus.COMPLETED
        self.executed_at = _utcnow()
        self.executed_by_user_id = executed_by_user_id
        self.random_seed = random_seed
        self.pool_hash = pool_hash
        self.ticket_pool_size = ticket_pool_size

    def cancel(self) -> None:
        if self.status is not SweepstakesDrawStatus.SCHEDULED:
            raise InvalidSweepstakesDrawStateError(
                f"Solo se cancela desde SCHEDULED (actual: {self.status.value})")
        self.status = SweepstakesDrawStatus.CANCELLED
