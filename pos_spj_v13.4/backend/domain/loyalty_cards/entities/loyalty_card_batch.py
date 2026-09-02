"""LoyaltyCardBatch — a print job for a fixed set of physical cards (master
prompt §43-44). `sheets_required` is DERIVED from `item_count` and the
imposition profile's `cards_per_sheet` (ceiling division) — never accepted
as caller input, same discipline as LOY-20's columns/rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import LoyaltyCardBatchStatus
from backend.domain.loyalty_cards.exceptions import (
    EmptyBatchError,
    InvalidLoyaltyCardBatchError,
    InvalidLoyaltyCardBatchStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCardBatch:
    id: str
    template_id: str
    imposition_profile_id: str
    item_count: int
    cards_per_sheet: int
    status: LoyaltyCardBatchStatus = LoyaltyCardBatchStatus.DRAFT
    created_by_user_id: str = ""
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.template_id:
            raise InvalidLoyaltyCardBatchError("template_id es obligatorio")
        if not self.imposition_profile_id:
            raise InvalidLoyaltyCardBatchError("imposition_profile_id es obligatorio")
        if self.item_count <= 0:
            raise EmptyBatchError("El lote requiere al menos una tarjeta")
        if self.cards_per_sheet <= 0:
            raise InvalidLoyaltyCardBatchError("cards_per_sheet debe ser positivo")

    @property
    def sheets_required(self) -> int:
        return -(-self.item_count // self.cards_per_sheet)  # ceiling division

    @classmethod
    def create(cls, template_id: str, imposition_profile_id: str, item_count: int,
               cards_per_sheet: int, *, created_by_user_id: str) -> "LoyaltyCardBatch":
        return cls(id=new_uuid(), template_id=template_id,
                    imposition_profile_id=imposition_profile_id, item_count=item_count,
                    cards_per_sheet=cards_per_sheet, created_by_user_id=created_by_user_id)

    def submit_for_approval(self) -> None:
        if self.status is not LoyaltyCardBatchStatus.DRAFT:
            raise InvalidLoyaltyCardBatchStateError(
                f"Solo se envía a aprobación desde DRAFT (actual: {self.status.value})")
        self.status = LoyaltyCardBatchStatus.PENDING_APPROVAL
        self.updated_at = _utcnow()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not LoyaltyCardBatchStatus.PENDING_APPROVAL:
            raise InvalidLoyaltyCardBatchStateError(
                f"Solo se aprueba desde PENDING_APPROVAL (actual: {self.status.value})")
        if approved_by_user_id == self.created_by_user_id:
            raise InvalidLoyaltyCardBatchStateError(
                "Quien aprueba no puede ser quien generó el lote (segregación de funciones)")
        self.status = LoyaltyCardBatchStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self.updated_at = _utcnow()

    def start_printing(self) -> None:
        if self.status is not LoyaltyCardBatchStatus.APPROVED:
            raise InvalidLoyaltyCardBatchStateError(
                f"Solo se inicia impresión desde APPROVED (actual: {self.status.value})")
        self.status = LoyaltyCardBatchStatus.PRINTING
        self.updated_at = _utcnow()

    def complete(self) -> None:
        if self.status is not LoyaltyCardBatchStatus.PRINTING:
            raise InvalidLoyaltyCardBatchStateError(
                f"Solo se completa desde PRINTING (actual: {self.status.value})")
        self.status = LoyaltyCardBatchStatus.COMPLETED
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status in (LoyaltyCardBatchStatus.COMPLETED, LoyaltyCardBatchStatus.CANCELLED):
            raise InvalidLoyaltyCardBatchStateError(
                f"No se puede cancelar desde {self.status.value}")
        self.status = LoyaltyCardBatchStatus.CANCELLED
        self.updated_at = _utcnow()
