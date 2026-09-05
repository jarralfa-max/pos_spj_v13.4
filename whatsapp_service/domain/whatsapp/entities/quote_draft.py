# domain/whatsapp/entities/quote_draft.py — WA-11 (§37 del prompt maestro)
"""
QuoteDraft — el equivalente de `OrderDraft` (WA-10) para cotizaciones.
Reutiliza `OrderDraftLine` (nada de su forma es específica de pedidos:
producto/cantidad/unidad/precio) en vez de duplicar una `QuoteDraftLine`
idéntica.

Ciclo de vida en DOS pasos, a diferencia de `OrderDraft`: capturar →
`QuotesApiClient.create()` (obtiene folio+vigencia reales del ERP, WA-9) →
luego, en un momento posterior, aceptar (→ `convert_to_order()`) o
rechazar. `OrderDraft.confirm()` colapsa "confirmar" y "crear" en un solo
paso porque así es como Orders funciona (§34); Quotes no funciona así
(§37).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.entities.order_draft import OrderDraftLine
from domain.whatsapp.enums import TERMINAL_QUOTE_DRAFT_STATUSES, QuoteDraftStatus
from domain.whatsapp.exceptions import WhatsAppDomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmptyQuoteDraftError(WhatsAppDomainError):
    pass


class QuoteDraftAlreadyFinalizedError(WhatsAppDomainError):
    pass


class QuoteDraftNotYetCreatedError(WhatsAppDomainError):
    """No se puede aceptar/rechazar una cotización que todavía no se creó
    en el ERP (sin `quote_external_id`/folio real)."""


@dataclass
class QuoteDraft:
    id: str
    conversation_id: str
    branch_id: Optional[str]
    customer_external_id: Optional[str]
    quote_external_id: Optional[str]
    folio: str
    status: QuoteDraftStatus
    lines: List[OrderDraftLine]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def start(cls, *, conversation_id: str, branch_id: Optional[str] = None) -> "QuoteDraft":
        if not conversation_id:
            raise ValueError("conversation_id es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            branch_id=branch_id,
            customer_external_id=None,
            quote_external_id=None,
            folio="",
            status=QuoteDraftStatus.CAPTURING,
            lines=[],
            created_at=now,
            updated_at=now,
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_QUOTE_DRAFT_STATUSES

    def _assert_capturing(self) -> None:
        if self.status != QuoteDraftStatus.CAPTURING:
            raise QuoteDraftAlreadyFinalizedError(
                f"QuoteDraft {self.id} está {self.status.value}; no se puede seguir capturando"
            )

    def add_line(
        self, *, product_external_id: str, product_name: str, quantity: float, unit: str, unit_price: float
    ) -> OrderDraftLine:
        self._assert_capturing()
        line = OrderDraftLine.create(
            product_external_id=product_external_id, product_name=product_name,
            quantity=quantity, unit=unit, unit_price=unit_price,
        )
        self.lines.append(line)
        self.updated_at = _utcnow()
        return line

    def set_customer(self, customer_external_id: str) -> None:
        self._assert_capturing()
        self.customer_external_id = customer_external_id
        self.updated_at = _utcnow()

    @property
    def total(self) -> float:
        return round(sum(line.subtotal for line in self.lines), 2)

    def mark_created(self, *, quote_external_id: str, folio: str = "") -> None:
        self._assert_capturing()
        if not self.lines:
            raise EmptyQuoteDraftError(f"QuoteDraft {self.id} no tiene líneas")
        self.quote_external_id = quote_external_id
        self.folio = folio
        self.status = QuoteDraftStatus.CREATED
        self.updated_at = _utcnow()

    def accept(self) -> None:
        if self.status != QuoteDraftStatus.CREATED:
            if not self.quote_external_id:
                raise QuoteDraftNotYetCreatedError(f"QuoteDraft {self.id} no se ha creado en el ERP todavía")
            raise QuoteDraftAlreadyFinalizedError(
                f"QuoteDraft {self.id} está {self.status.value}; no se puede aceptar"
            )
        self.status = QuoteDraftStatus.ACCEPTED
        self.updated_at = _utcnow()

    def reject(self) -> None:
        if self.status != QuoteDraftStatus.CREATED:
            if not self.quote_external_id:
                raise QuoteDraftNotYetCreatedError(f"QuoteDraft {self.id} no se ha creado en el ERP todavía")
            raise QuoteDraftAlreadyFinalizedError(
                f"QuoteDraft {self.id} está {self.status.value}; no se puede rechazar"
            )
        self.status = QuoteDraftStatus.REJECTED
        self.updated_at = _utcnow()

    def expire(self) -> None:
        if self.is_terminal():
            raise QuoteDraftAlreadyFinalizedError(f"QuoteDraft {self.id} ya está {self.status.value}")
        self.status = QuoteDraftStatus.EXPIRED
        self.updated_at = _utcnow()
