"""SweepstakesTicket — a printable/physical representation of one chance
already earned via a `SweepstakesEntry` (master prompt §28).

§28's own rule, enforced at the type level: `entry_id` is a required,
non-optional field — a ticket literally cannot be constructed without
pointing at an already-existing entry (the application layer additionally
verifies the entry row is real and belongs to the same campaign before
calling `issue()`; that check cannot live in the entity itself since it
requires a repository lookup).

Reprinting NEVER creates a new ticket/entry — `record_print()` mutates this
same row (`print_count`, `last_printed_at`) rather than the application
layer creating a second `SweepstakesTicket`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.sweepstakes.enums import SweepstakesTicketStatus
from backend.domain.sweepstakes.exceptions import (
    InvalidSweepstakesTicketStateError,
    TicketRequiresExistingEntryError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesTicket:
    id: str
    campaign_id: str
    entry_id: str
    customer_id: str
    ticket_number: str
    status: SweepstakesTicketStatus = SweepstakesTicketStatus.ISSUED
    print_count: int = 0
    first_printed_at: str | None = None
    last_printed_at: str | None = None
    void_reason: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise TicketRequiresExistingEntryError("campaign_id es obligatorio")
        if not self.entry_id:
            raise TicketRequiresExistingEntryError(
                "Un boleto no puede existir sin una SweepstakesEntry previa (§28)")
        if not self.customer_id:
            raise InvalidSweepstakesTicketStateError("customer_id es obligatorio")
        if not self.ticket_number or not self.ticket_number.strip():
            raise InvalidSweepstakesTicketStateError("ticket_number es obligatorio")
        if self.print_count < 0:
            raise InvalidSweepstakesTicketStateError("print_count no puede ser negativo")

    @classmethod
    def issue(cls, campaign_id: str, entry_id: str, customer_id: str,
              ticket_number: str) -> "SweepstakesTicket":
        return cls(id=new_uuid(), campaign_id=campaign_id, entry_id=entry_id,
                    customer_id=customer_id, ticket_number=ticket_number.strip())

    def record_print(self) -> None:
        """First call transitions ISSUED→PRINTED; every subsequent call is a
        reprint of this SAME ticket — never a new entry or ticket row."""
        if self.status is SweepstakesTicketStatus.VOID:
            raise InvalidSweepstakesTicketStateError("No se puede imprimir un boleto VOID")
        now = _utcnow()
        if self.first_printed_at is None:
            self.first_printed_at = now
        self.last_printed_at = now
        self.print_count += 1
        self.status = SweepstakesTicketStatus.PRINTED

    def void(self, reason: str) -> None:
        if self.status is SweepstakesTicketStatus.VOID:
            raise InvalidSweepstakesTicketStateError("El boleto ya está VOID")
        if not (reason or "").strip():
            raise InvalidSweepstakesTicketStateError("Anular requiere un motivo")
        self.status = SweepstakesTicketStatus.VOID
        self.void_reason = reason

    def is_eligible(self) -> bool:
        return self.status in (SweepstakesTicketStatus.ISSUED, SweepstakesTicketStatus.PRINTED)
