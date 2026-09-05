# tests/test_quote_draft_service.py — WA-11
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.quote_draft_service import ProductNotFoundError, QuoteDraftService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.quote_draft import EmptyQuoteDraftError, QuoteDraft
from domain.whatsapp.enums import IdempotencyStatus, QuoteDraftStatus
from domain.whatsapp.erp_ports import OrderRef, ProductRef, QuoteRef
from infrastructure.persistence.sqlite_idempotency_repository import SqliteWhatsAppIdempotencyRepository
from infrastructure.persistence.sqlite_quote_draft_repository import SqliteWhatsAppQuoteDraftRepository


class _FakeCatalog:
    def __init__(self, results=None):
        self._results = results if results is not None else [
            ProductRef(external_id="p1", name="Bistec de res", unit="kg", price=180.0, stock=10.0)
        ]

    async def search(self, query, max_results=5):
        return self._results[:max_results]


class _FakeQuotes:
    def __init__(self, *, create_should_fail=False, convert_should_fail=False):
        self.create_calls = []
        self.convert_calls = []
        self._create_should_fail = create_should_fail
        self._convert_should_fail = convert_should_fail

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self._create_should_fail:
            raise RuntimeError("ERP no disponible")
        n = len(self.create_calls)
        return QuoteRef(external_id=f"quote-{n}", folio=f"COT-{n:03d}", valid_until="2026-09-08")

    async def convert_to_order(self, quote_id, user="whatsapp"):
        self.convert_calls.append((quote_id, user))
        if self._convert_should_fail:
            raise RuntimeError("ERP no disponible")
        n = len(self.convert_calls)
        return OrderRef(external_id=f"order-{n}", status="confirmada", folio=f"F-{n:03d}")


class _FakeRoot:
    def __init__(self, conn, *, catalog=None, quotes=None):
        self.quote_drafts = SqliteWhatsAppQuoteDraftRepository(conn)
        self.idempotency = SqliteWhatsAppIdempotencyRepository(conn)
        self.catalog = catalog or _FakeCatalog()
        self.quotes = quotes or _FakeQuotes()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestCaptureAndCreate:
    def test_start_draft_persists(self, conn):
        service = QuoteDraftService(_FakeRoot(conn))
        draft = service.start_draft(conversation_id="conv-1")
        assert draft.status == QuoteDraftStatus.CAPTURING

    def test_add_product_by_search(self, conn):
        root = _FakeRoot(conn)
        service = QuoteDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=2))
        assert draft.total == 360.0

    def test_add_product_by_search_raises_when_not_found(self, conn):
        root = _FakeRoot(conn, catalog=_FakeCatalog(results=[]))
        service = QuoteDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        with pytest.raises(ProductNotFoundError):
            _run(service.add_product_by_search(draft, query="nada", quantity=1))

    def test_create_quote_sets_folio_from_erp(self, conn):
        quotes = _FakeQuotes()
        root = _FakeRoot(conn, quotes=quotes)
        service = QuoteDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=1))

        result = _run(service.create_quote(draft, customer_external_id="cust-1"))

        assert result.deduplicated is False
        assert result.quote.folio == "COT-001"
        assert draft.status == QuoteDraftStatus.CREATED
        assert draft.folio == "COT-001"
        assert len(quotes.create_calls) == 1

    def test_create_quote_on_empty_draft_raises(self, conn):
        service = QuoteDraftService(_FakeRoot(conn))
        draft = service.start_draft(conversation_id="conv-1")
        with pytest.raises(EmptyQuoteDraftError):
            _run(service.create_quote(draft, customer_external_id="cust-1"))

    def test_second_create_attempt_with_same_content_is_deduplicated(self, conn):
        quotes = _FakeQuotes()
        root = _FakeRoot(conn, quotes=quotes)
        service = QuoteDraftService(root)

        first = QuoteDraft.start(conversation_id="conv-1")
        first.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        root.quote_drafts.save(first)
        _run(service.create_quote(first, customer_external_id="cust-1"))

        second = QuoteDraft.start(conversation_id="conv-1")
        second.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        root.quote_drafts.save(second)
        result = _run(service.create_quote(second, customer_external_id="cust-1"))

        assert result.deduplicated is True
        assert len(quotes.create_calls) == 1
        assert second.status == QuoteDraftStatus.CREATED

    def test_failed_creation_marks_idempotency_failed(self, conn):
        root = _FakeRoot(conn, quotes=_FakeQuotes(create_should_fail=True))
        service = QuoteDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=1))

        with pytest.raises(RuntimeError):
            _run(service.create_quote(draft, customer_external_id="cust-1"))

        assert draft.status == QuoteDraftStatus.CAPTURING


class TestAcceptReject:
    def _created_draft(self, root, service):
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=1))
        _run(service.create_quote(draft, customer_external_id="cust-1"))
        return draft

    def test_accept_converts_to_order(self, conn):
        quotes = _FakeQuotes()
        root = _FakeRoot(conn, quotes=quotes)
        service = QuoteDraftService(root)
        draft = self._created_draft(root, service)

        result = _run(service.accept(draft))

        assert result.deduplicated is False
        assert result.order.external_id == "order-1"
        assert draft.status == QuoteDraftStatus.ACCEPTED
        assert quotes.convert_calls == [(draft.quote_external_id, "whatsapp")]

    def test_accept_never_touches_sql_directly(self, conn):
        """§37: "no convertir directamente mediante SQL" — la única forma
        de aceptar es a través de `QuotesApiClient.convert_to_order()`."""
        quotes = _FakeQuotes()
        root = _FakeRoot(conn, quotes=quotes)
        service = QuoteDraftService(root)
        draft = self._created_draft(root, service)
        _run(service.accept(draft))
        assert len(quotes.convert_calls) == 1

    def test_double_accept_is_deduplicated(self, conn):
        quotes = _FakeQuotes()
        root = _FakeRoot(conn, quotes=quotes)
        service = QuoteDraftService(root)
        draft = self._created_draft(root, service)

        first = _run(service.accept(draft))
        second = _run(service.accept(draft))

        assert first.order.external_id == second.order.external_id
        assert len(quotes.convert_calls) == 1

    def test_reject_sets_rejected_status(self, conn):
        root = _FakeRoot(conn)
        service = QuoteDraftService(root)
        draft = self._created_draft(root, service)
        service.reject(draft)
        assert draft.status == QuoteDraftStatus.REJECTED

    def test_failed_conversion_marks_idempotency_failed_and_reraises(self, conn):
        root = _FakeRoot(conn, quotes=_FakeQuotes(convert_should_fail=True))
        service = QuoteDraftService(root)
        draft = self._created_draft(root, service)

        with pytest.raises(RuntimeError):
            _run(service.accept(draft))

        assert draft.status == QuoteDraftStatus.CREATED  # nunca se marcó aceptada
