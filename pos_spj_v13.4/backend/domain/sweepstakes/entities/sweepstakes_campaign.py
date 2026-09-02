"""SweepstakesCampaign — the top-level sweepstakes/rifa record (master
prompt §27). Separate bounded context from the legacy `raffles` table
(`migrations/standalone/113_raffle_subsystem.py`) — same promotional
concept, rebuilt with Decimal money, a real state machine, and segregation
of duties on approval (mirrors `backend.domain.loyalty.entities.campaign.
Campaign`'s own lifecycle shape)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.sweepstakes.enums import SweepstakesCampaignStatus
from backend.domain.sweepstakes.exceptions import (
    InvalidSweepstakesCampaignError,
    InvalidSweepstakesCampaignStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesCampaign:
    id: str
    code: str
    name: str
    description: str = ""
    ticket_price: Decimal = Decimal("0")
    max_tickets_per_customer: int = 0
    branch_id: str | None = None
    status: SweepstakesCampaignStatus = SweepstakesCampaignStatus.DRAFT
    starts_at: str | None = None
    ends_at: str | None = None
    created_by_user_id: str = ""
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise InvalidSweepstakesCampaignError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidSweepstakesCampaignError("name es obligatorio")
        if isinstance(self.ticket_price, (bool, float)):
            raise InvalidSweepstakesCampaignError("ticket_price debe ser Decimal, nunca float")
        self.ticket_price = Decimal(str(self.ticket_price))
        if self.ticket_price < 0:
            raise InvalidSweepstakesCampaignError("ticket_price no puede ser negativo")
        if self.max_tickets_per_customer < 0:
            raise InvalidSweepstakesCampaignError("max_tickets_per_customer no puede ser negativo")

    @classmethod
    def create(cls, code: str, name: str, *, created_by_user_id: str, **kwargs) -> "SweepstakesCampaign":
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                    created_by_user_id=created_by_user_id, **kwargs)

    def submit_for_approval(self) -> None:
        if self.status is not SweepstakesCampaignStatus.DRAFT:
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se envía a aprobación desde DRAFT (actual: {self.status.value})")
        self.status = SweepstakesCampaignStatus.PENDING_APPROVAL
        self.updated_at = _utcnow()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not SweepstakesCampaignStatus.PENDING_APPROVAL:
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se aprueba desde PENDING_APPROVAL (actual: {self.status.value})")
        if approved_by_user_id == self.created_by_user_id:
            raise InvalidSweepstakesCampaignStateError(
                "Quien aprueba no puede ser quien creó la campaña (segregación de funciones)")
        self.status = SweepstakesCampaignStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self.updated_at = _utcnow()

    def activate(self) -> None:
        if self.status is not SweepstakesCampaignStatus.APPROVED:
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se activa desde APPROVED (actual: {self.status.value})")
        self.status = SweepstakesCampaignStatus.ACTIVE
        self.updated_at = _utcnow()

    def pause(self) -> None:
        if self.status is not SweepstakesCampaignStatus.ACTIVE:
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se pausa desde ACTIVE (actual: {self.status.value})")
        self.status = SweepstakesCampaignStatus.PAUSED
        self.updated_at = _utcnow()

    def resume(self) -> None:
        if self.status is not SweepstakesCampaignStatus.PAUSED:
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se reanuda desde PAUSED (actual: {self.status.value})")
        self.status = SweepstakesCampaignStatus.ACTIVE
        self.updated_at = _utcnow()

    def mark_drawn(self) -> None:
        if self.status not in (SweepstakesCampaignStatus.ACTIVE, SweepstakesCampaignStatus.PAUSED):
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se marca DRAWN desde ACTIVE/PAUSED (actual: {self.status.value})")
        self.status = SweepstakesCampaignStatus.DRAWN
        self.updated_at = _utcnow()

    def close(self) -> None:
        if self.status is not SweepstakesCampaignStatus.DRAWN:
            raise InvalidSweepstakesCampaignStateError(
                f"Solo se cierra desde DRAWN (actual: {self.status.value})")
        self.status = SweepstakesCampaignStatus.CLOSED
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status in (SweepstakesCampaignStatus.CLOSED, SweepstakesCampaignStatus.CANCELLED):
            raise InvalidSweepstakesCampaignStateError(
                f"No se puede cancelar desde {self.status.value}")
        self.status = SweepstakesCampaignStatus.CANCELLED
        self.updated_at = _utcnow()

    def is_active(self) -> bool:
        return self.status is SweepstakesCampaignStatus.ACTIVE

    def accepts_entries(self) -> bool:
        return self.status is SweepstakesCampaignStatus.ACTIVE
