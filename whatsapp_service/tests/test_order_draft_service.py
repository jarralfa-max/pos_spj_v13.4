# tests/test_order_draft_service.py — WA-10
"""Integración real del "cerebro" de Pedidos: `OrderDraftService` contra
repositorios SQLite reales (WA-3/WA-10) y clientes ERP falsos (el
contrato de WA-9, no su implementación real — eso ya lo prueba
`test_erp_bridge_clients.py`)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.order_draft_service import OrderDraftService, ProductNotFoundError
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.order_draft import EmptyOrderDraftError, OrderDraft
from domain.whatsapp.enums import DeliveryMethod, IdempotencyStatus, OrderDraftStatus
from domain.whatsapp.erp_ports import OrderRef, ProductRef
from infrastructure.persistence.sqlite_idempotency_repository import SqliteWhatsAppIdempotencyRepository
from infrastructure.persistence.sqlite_order_draft_repository import SqliteWhatsAppOrderDraftRepository


class _FakeCatalog:
    def __init__(self, results=None):
        self._results = results if results is not None else [
            ProductRef(external_id="p1", name="Bistec de res", unit="kg", price=180.0, stock=10.0)
        ]
        self.search_calls = []

    async def search(self, query, max_results=5):
        self.search_calls.append(query)
        return self._results[:max_results]


class _FakeOrders:
    def __init__(self, *, should_fail=False):
        self.create_calls = []
        self._should_fail = should_fail

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self._should_fail:
            raise RuntimeError("ERP no disponible")
        n = len(self.create_calls)
        return OrderRef(external_id=f"order-{n}", status="pendiente_wa", folio=f"F-{n:03d}")


class _FakeRoot:
    def __init__(self, conn, *, catalog=None, orders=None):
        self.order_drafts = SqliteWhatsAppOrderDraftRepository(conn)
        self.idempotency = SqliteWhatsAppIdempotencyRepository(conn)
        self.catalog = catalog or _FakeCatalog()
        self.orders = orders or _FakeOrders()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestStartDraft:
    def test_persists_a_building_draft(self, conn):
        service = OrderDraftService(_FakeRoot(conn))
        draft = service.start_draft(conversation_id="conv-1", branch_id="branch-1")
        assert draft.status == OrderDraftStatus.BUILDING

        fetched = _FakeRoot(conn).order_drafts.get_by_id(draft.id)
        assert fetched is not None


class TestProductSelection:
    def test_add_product_by_search_adds_first_match(self, conn):
        root = _FakeRoot(conn)
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        line = _run(service.add_product_by_search(draft, query="bistec", quantity=2))
        assert line.product_name == "Bistec de res"
        assert draft.total == 360.0

    def test_raises_when_catalog_has_no_match(self, conn):
        root = _FakeRoot(conn, catalog=_FakeCatalog(results=[]))
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        with pytest.raises(ProductNotFoundError):
            _run(service.add_product_by_search(draft, query="algo raro", quantity=1))

    def test_add_product_persists_line(self, conn):
        root = _FakeRoot(conn)
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=1))
        fetched = root.order_drafts.get_by_id(draft.id)
        assert len(fetched.lines) == 1


class TestDeliveryMethod:
    def test_set_delivery_method_persists(self, conn):
        root = _FakeRoot(conn)
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        service.set_delivery_method(draft, DeliveryMethod.DELIVERY)
        fetched = root.order_drafts.get_by_id(draft.id)
        assert fetched.delivery_method == DeliveryMethod.DELIVERY


class TestConfirmation:
    def test_confirm_creates_order_and_marks_draft_confirmed(self, conn):
        orders = _FakeOrders()
        root = _FakeRoot(conn, orders=orders)
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1", branch_id="branch-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=2))
        service.set_delivery_method(draft, DeliveryMethod.PICKUP)

        result = _run(service.confirm(draft, customer_external_id="cust-1"))

        assert result.deduplicated is False
        assert result.order.external_id == "order-1"
        assert draft.status == OrderDraftStatus.CONFIRMED
        assert len(orders.create_calls) == 1
        assert orders.create_calls[0]["customer_id"] == "cust-1"
        assert orders.create_calls[0]["branch_id"] == "branch-1"

    def test_confirm_empty_draft_raises(self, conn):
        root = _FakeRoot(conn)
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        with pytest.raises(EmptyOrderDraftError):
            _run(service.confirm(draft, customer_external_id="cust-1"))

    def test_confirm_records_idempotency_as_completed(self, conn):
        root = _FakeRoot(conn)
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=1))
        _run(service.confirm(draft, customer_external_id="cust-1"))

        from application.order_draft_service import _fingerprint

        record = root.idempotency.get_by_fingerprint(_fingerprint(draft))
        assert record.status == IdempotencyStatus.COMPLETED
        assert record.result_reference == "order-1"

    def test_second_confirm_attempt_with_same_content_is_deduplicated(self, conn):
        """Simula la reconstrucción de un borrador NUEVO con el mismo
        contenido (mismo conversation_id + mismas líneas + mismo método de
        entrega) — el escenario real de "el cliente escribe 'confirmar' dos
        veces" en un canal que reconstruye el draft desde cero cada vez."""
        orders = _FakeOrders()
        root = _FakeRoot(conn, orders=orders)
        service = OrderDraftService(root)

        first_draft = OrderDraft.start(conversation_id="conv-1")
        first_draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        root.order_drafts.save(first_draft)
        _run(service.confirm(first_draft, customer_external_id="cust-1"))

        second_draft = OrderDraft.start(conversation_id="conv-1")
        second_draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        root.order_drafts.save(second_draft)
        result = _run(service.confirm(second_draft, customer_external_id="cust-1"))

        assert result.deduplicated is True
        assert result.order.external_id == "order-1"
        assert len(orders.create_calls) == 1  # nunca se llamó una segunda vez
        assert second_draft.status == OrderDraftStatus.CONFIRMED

    def test_different_cart_contents_produce_different_orders(self, conn):
        orders = _FakeOrders()
        root = _FakeRoot(conn, orders=orders)
        service = OrderDraftService(root)

        draft_a = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft_a, query="bistec", quantity=1))
        _run(service.confirm(draft_a, customer_external_id="cust-1"))

        draft_b = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft_b, query="bistec", quantity=3))  # cantidad distinta
        result_b = _run(service.confirm(draft_b, customer_external_id="cust-1"))

        assert result_b.deduplicated is False
        assert len(orders.create_calls) == 2

    def test_failed_order_creation_marks_idempotency_failed_and_reraises(self, conn):
        root = _FakeRoot(conn, orders=_FakeOrders(should_fail=True))
        service = OrderDraftService(root)
        draft = service.start_draft(conversation_id="conv-1")
        _run(service.add_product_by_search(draft, query="bistec", quantity=1))

        with pytest.raises(RuntimeError):
            _run(service.confirm(draft, customer_external_id="cust-1"))

        from application.order_draft_service import _fingerprint

        record = root.idempotency.get_by_fingerprint(_fingerprint(draft))
        assert record.status == IdempotencyStatus.FAILED
        assert draft.status == OrderDraftStatus.BUILDING  # nunca se marcó confirmado
