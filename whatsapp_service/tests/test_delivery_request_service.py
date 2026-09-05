# tests/test_delivery_request_service.py — WA-13
"""`DeliveryRequestService` contra un `idempotency`/`delivery_requests`
repository SQLite real (WA-3/WA-13) y un `DeliveryApiClient` falso (el
contrato de WA-9, no su implementación real)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.delivery_request_service import DeliveryRequestService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from infrastructure.persistence.sqlite_delivery_request_repository import (
    SqliteWhatsAppDeliveryRequestRepository,
)
from infrastructure.persistence.sqlite_idempotency_repository import SqliteWhatsAppIdempotencyRepository


class _FakeDelivery:
    def __init__(self, *, results=None):
        self.calls = []
        self._results = list(results) if results is not None else [True]

    async def schedule(self, *, order_id, address, delivery_date="", customer_phone=""):
        self.calls.append((order_id, address, delivery_date, customer_phone))
        if not self._results:
            return True
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeRoot:
    def __init__(self, conn, *, delivery=None):
        self.idempotency = SqliteWhatsAppIdempotencyRepository(conn)
        self.delivery_requests = SqliteWhatsAppDeliveryRequestRepository(conn)
        self.delivery = delivery or _FakeDelivery()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestRequestDelivery:
    def test_schedules_successfully(self, conn):
        delivery = _FakeDelivery(results=[True])
        service = DeliveryRequestService(_FakeRoot(conn, delivery=delivery))

        result = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))

        assert result.scheduled is True
        assert result.deduplicated is False
        assert len(delivery.calls) == 1

    def test_duplicate_request_does_not_schedule_twice(self, conn):
        """El caso real de WA-13: el cliente pide "programa mi entrega" dos
        veces (dos mensajes distintos) con el mismo pedido/dirección — la
        segunda NO debe volver a llamar a `DeliveryApiClient.schedule()`."""
        delivery = _FakeDelivery(results=[True])
        root = _FakeRoot(conn, delivery=delivery)
        service = DeliveryRequestService(root)

        first = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))
        second = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))

        assert first.deduplicated is False
        assert second.deduplicated is True
        assert second.scheduled is True
        assert len(delivery.calls) == 1  # nunca se llamó una segunda vez

    def test_different_address_is_not_deduplicated(self, conn):
        delivery = _FakeDelivery(results=[True, True])
        service = DeliveryRequestService(_FakeRoot(conn, delivery=delivery))

        _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))
        result = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 2 #45",
        ))

        assert result.deduplicated is False
        assert len(delivery.calls) == 2

    def test_erp_returning_false_marks_failed(self, conn):
        delivery = _FakeDelivery(results=[False])
        service = DeliveryRequestService(_FakeRoot(conn, delivery=delivery))

        result = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))

        assert result.scheduled is False
        assert result.deduplicated is False
        from domain.whatsapp.enums import DeliveryRequestStatus
        assert result.request.status == DeliveryRequestStatus.FAILED

    def test_retry_after_failure_succeeds_and_is_not_deduplicated(self, conn):
        """Un fallo previo no debe bloquear un reintento real con el mismo
        contenido — a diferencia de dejarlo atrapado en FAILED para
        siempre."""
        delivery = _FakeDelivery(results=[False, True])
        root = _FakeRoot(conn, delivery=delivery)
        service = DeliveryRequestService(root)

        first = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))
        second = _run(service.request_delivery(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        ))

        assert first.scheduled is False
        assert second.scheduled is True
        assert second.deduplicated is False
        assert len(delivery.calls) == 2

    def test_exception_marks_request_failed_and_reraises(self, conn):
        delivery = _FakeDelivery(results=[RuntimeError("ERP no disponible")])
        service = DeliveryRequestService(_FakeRoot(conn, delivery=delivery))

        with pytest.raises(RuntimeError):
            _run(service.request_delivery(
                conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
            ))

        from application.idempotency_fingerprint import compute_fingerprint
        record = _FakeRoot(conn).idempotency.get_by_fingerprint(
            compute_fingerprint("SCHEDULE_DELIVERY", "order-1", "Calle 1 #23", "")
        )
        from domain.whatsapp.enums import IdempotencyStatus
        assert record.status == IdempotencyStatus.FAILED
