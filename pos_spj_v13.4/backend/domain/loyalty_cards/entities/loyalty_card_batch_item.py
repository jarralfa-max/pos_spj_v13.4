"""LoyaltyCardBatchItem — one physical card's slot within a batch (master
prompt §43-44). `sheet_number`/`position_in_sheet` are assigned at creation
from the item's sequential index and the batch's `cards_per_sheet` — never
recomputed later, so a reprint never silently reshuffles a card's physical
position on its sheet."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import LoyaltyCardBatchItemStatus
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardBatchItemStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCardBatchItem:
    id: str
    batch_id: str
    card_id: str
    sheet_number: int
    position_in_sheet: int
    status: LoyaltyCardBatchItemStatus = LoyaltyCardBatchItemStatus.PENDING
    failure_reason: str | None = None
    printed_at: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.batch_id:
            raise InvalidLoyaltyCardBatchItemStateError("batch_id es obligatorio")
        if not self.card_id:
            raise InvalidLoyaltyCardBatchItemStateError("card_id es obligatorio")
        if self.sheet_number <= 0:
            raise InvalidLoyaltyCardBatchItemStateError("sheet_number debe ser positivo")
        if self.position_in_sheet <= 0:
            raise InvalidLoyaltyCardBatchItemStateError("position_in_sheet debe ser positivo")

    @classmethod
    def create_for_index(cls, batch_id: str, card_id: str, *, index: int,
                          cards_per_sheet: int) -> "LoyaltyCardBatchItem":
        """`index` is the item's 0-based sequential position within the
        batch — sheet/position are derived from it, never supplied
        independently, so they can never disagree with the item's actual
        order in the batch."""
        sheet_number = (index // cards_per_sheet) + 1
        position_in_sheet = (index % cards_per_sheet) + 1
        return cls(id=new_uuid(), batch_id=batch_id, card_id=card_id, sheet_number=sheet_number,
                   position_in_sheet=position_in_sheet)

    def mark_printed(self) -> None:
        if self.status is not LoyaltyCardBatchItemStatus.PENDING:
            raise InvalidLoyaltyCardBatchItemStateError(
                f"Solo se marca impreso desde PENDING (actual: {self.status.value})")
        self.status = LoyaltyCardBatchItemStatus.PRINTED
        self.printed_at = _utcnow()

    def mark_failed(self, reason: str) -> None:
        if self.status is not LoyaltyCardBatchItemStatus.PENDING:
            raise InvalidLoyaltyCardBatchItemStateError(
                f"Solo se marca fallido desde PENDING (actual: {self.status.value})")
        if not (reason or "").strip():
            raise InvalidLoyaltyCardBatchItemStateError("El fallo requiere un motivo")
        self.status = LoyaltyCardBatchItemStatus.FAILED
        self.failure_reason = reason
