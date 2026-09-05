# application/quote_draft_service.py — WA-11 (§37, §19 del prompt maestro)
"""
QuoteDraftService — captura → `QuotesApiClient.create()` (folio/vigencia
reales, WA-9) → aceptar (`convert_to_order()`) o rechazar. Mismo criterio
de idempotencia de negocio que `OrderDraftService` (WA-10) — reutiliza
`compute_fingerprint()`, no reinventa el algoritmo. "No convertir
directamente mediante SQL" (§37): `accept()` SIEMPRE pasa por
`QuotesApiClient.convert_to_order()`, nunca toca una tabla.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from application.idempotency_fingerprint import compute_fingerprint
from domain.whatsapp.entities.business_operation import BusinessOperationIdempotencyRecord
from domain.whatsapp.entities.order_draft import OrderDraftLine
from domain.whatsapp.entities.quote_draft import QuoteDraft, QuoteDraftStatus
from domain.whatsapp.erp_ports import OrderRef, ProductRef, QuoteRef


class ProductNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreateQuoteResult:
    quote: QuoteRef
    deduplicated: bool


@dataclass(frozen=True)
class AcceptQuoteResult:
    order: OrderRef
    deduplicated: bool


def _capture_fingerprint(draft: QuoteDraft) -> str:
    line_signature = "|".join(
        f"{line.product_external_id}:{line.quantity}"
        for line in sorted(draft.lines, key=lambda l: l.product_external_id)
    )
    return compute_fingerprint("CREATE_QUOTE", draft.conversation_id, line_signature)


def _accept_fingerprint(draft: QuoteDraft) -> str:
    return compute_fingerprint("ACCEPT_QUOTE", draft.quote_external_id or draft.id)


class QuoteDraftService:
    def __init__(self, root) -> None:
        self._root = root

    def start_draft(self, *, conversation_id: str, branch_id: Optional[str] = None) -> QuoteDraft:
        draft = QuoteDraft.start(conversation_id=conversation_id, branch_id=branch_id)
        self._root.quote_drafts.save(draft)
        return draft

    async def add_product_by_search(self, draft: QuoteDraft, *, query: str, quantity: float) -> OrderDraftLine:
        results = await self._root.catalog.search(query, max_results=1)
        if not results:
            raise ProductNotFoundError(f"Sin coincidencias de catálogo para {query!r}")
        return self.add_product(draft, product=results[0], quantity=quantity)

    def add_product(self, draft: QuoteDraft, *, product: ProductRef, quantity: float) -> OrderDraftLine:
        line = draft.add_line(
            product_external_id=product.external_id, product_name=product.name,
            quantity=quantity, unit=product.unit, unit_price=product.price,
        )
        self._root.quote_drafts.save(draft)
        return line

    async def create_quote(self, draft: QuoteDraft, *, customer_external_id: str) -> CreateQuoteResult:
        fingerprint = _capture_fingerprint(draft)
        existing = self._root.idempotency.get_by_fingerprint(fingerprint)
        if existing is not None and existing.result_reference:
            if draft.status == QuoteDraftStatus.CAPTURING:
                draft.set_customer(customer_external_id)
                draft.mark_created(quote_external_id=existing.result_reference)
                self._root.quote_drafts.save(draft)
            return CreateQuoteResult(quote=QuoteRef(external_id=existing.result_reference), deduplicated=True)

        draft.set_customer(customer_external_id)
        record = existing or BusinessOperationIdempotencyRecord.start(
            operation_type="CREATE_QUOTE", aggregate_type="QUOTE_DRAFT",
            aggregate_id=draft.id, fingerprint=fingerprint,
        )
        if existing is None:
            self._root.idempotency.save(record)

        items = [
            {"producto_id": line.product_external_id, "cantidad": line.quantity, "unidad": line.unit, "precio_unitario": line.unit_price}
            for line in draft.lines
        ]
        try:
            quote_ref = await self._root.quotes.create(items=items, customer_id=customer_external_id)
        except Exception:
            record.fail()
            self._root.idempotency.save(record)
            raise

        record.complete(result_reference=quote_ref.external_id)
        self._root.idempotency.save(record)

        draft.mark_created(quote_external_id=quote_ref.external_id, folio=quote_ref.folio)
        self._root.quote_drafts.save(draft)
        return CreateQuoteResult(quote=quote_ref, deduplicated=False)

    async def accept(self, draft: QuoteDraft) -> AcceptQuoteResult:
        fingerprint = _accept_fingerprint(draft)
        existing = self._root.idempotency.get_by_fingerprint(fingerprint)
        if existing is not None and existing.result_reference:
            if draft.status != QuoteDraftStatus.ACCEPTED:
                draft.accept()
                self._root.quote_drafts.save(draft)
            return AcceptQuoteResult(
                order=OrderRef(external_id=existing.result_reference, status="confirmada"), deduplicated=True
            )

        record = existing or BusinessOperationIdempotencyRecord.start(
            operation_type="ACCEPT_QUOTE", aggregate_type="QUOTE_DRAFT",
            aggregate_id=draft.id, fingerprint=fingerprint,
        )
        if existing is None:
            self._root.idempotency.save(record)

        try:
            order_ref = await self._root.quotes.convert_to_order(draft.quote_external_id, "whatsapp")
        except Exception:
            record.fail()
            self._root.idempotency.save(record)
            raise

        record.complete(result_reference=order_ref.external_id)
        self._root.idempotency.save(record)

        draft.accept()
        self._root.quote_drafts.save(draft)
        return AcceptQuoteResult(order=order_ref, deduplicated=False)

    def reject(self, draft: QuoteDraft) -> QuoteDraft:
        draft.reject()
        self._root.quote_drafts.save(draft)
        return draft
