"""RFQ / quotation use cases (§58 quotes) — request quotes from suppliers,
capture their answers, and award one. Comparison/award logic is in the domain;
the widget never decides. Awarding is audited and emits its canonical event."""

from __future__ import annotations

import json

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import (
    RequestForQuotation,
    SupplierQuote,
    SupplierQuoteLine,
)
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _year() -> int:
    from datetime import date
    return date.today().year


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class CreateRfqUseCase:
    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                supplier_ids: list[str]) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RFQ_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            try:
                rfq = RequestForQuotation.create(
                    uow.sequences.next_number("RFQ", _year()), tuple(supplier_ids))
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.rfqs.save_rfq(rfq)
            uow.rfqs.set_rfq_operation_id(rfq.id, operation_id)
            uow.audit.record(action=ProcurementEvents.RFQ_CREATED, actor_user_id=actor_user_id,
                             document_id=rfq.id, operation_id=operation_id)
            _emit(uow, ProcurementEvents.RFQ_CREATED, document_id=rfq.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  document_number=rfq.document_number)
        return ProcurementResult.ok("RFQ creada", entity_id=rfq.id, operation_id=operation_id,
                                    document_number=rfq.document_number)


class CaptureSupplierQuoteUseCase:
    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, rfq_id: str,
                supplier_id: str, lines: list[dict], lead_time_days: int = 0,
                currency_code: str = "MXN") -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.QUOTE_CAPTURE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            if uow.rfqs.get_rfq(rfq_id) is None:
                return ProcurementResult.fail("RFQ inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                quote = SupplierQuote.create(rfq_id, supplier_id,
                                             lead_time_days=lead_time_days,
                                             currency_code=currency_code)
                for raw in lines:
                    quote.lines.append(SupplierQuoteLine.create(
                        raw["product_id"], str(raw["quantity"]),
                        Money(str(raw["unit_price"]), currency_code)))
            except (ProcurementDomainError, ValueError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.rfqs.save_quote(quote)
            uow.audit.record(action=ProcurementEvents.SUPPLIER_QUOTE_RECEIVED,
                             actor_user_id=actor_user_id, document_id=quote.id,
                             operation_id=operation_id)
            _emit(uow, ProcurementEvents.SUPPLIER_QUOTE_RECEIVED, document_id=quote.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=supplier_id, total=str(quote.total().amount))
        return ProcurementResult.ok("Cotización capturada", entity_id=quote.id,
                                    operation_id=operation_id, total=str(quote.total().amount))


class AwardSupplierQuoteUseCase:
    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, quote_id: str,
                reason: str = "") -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.QUOTE_AWARD)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            quote = uow.rfqs.get_quote(quote_id)
            if quote is None:
                return ProcurementResult.fail("Cotización inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            quote.award()
            uow.rfqs.save_quote(quote)
            uow.audit.record(action=ProcurementEvents.SUPPLIER_QUOTE_AWARDED,
                             actor_user_id=actor_user_id, document_id=quote.id,
                             reason=reason, operation_id=operation_id)
            _emit(uow, ProcurementEvents.SUPPLIER_QUOTE_AWARDED, document_id=quote.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=quote.supplier_id, rfq_id=quote.rfq_id)
        return ProcurementResult.ok("Cotización adjudicada", entity_id=quote.id,
                                    operation_id=operation_id)
