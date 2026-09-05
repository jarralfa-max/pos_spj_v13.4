# tests/test_notification_service.py — WA-18
"""`NotificationService` contra `OutboundMessageService`/`OutboundDispatcher`
reales (WA-17, sobre SQLite real) y un `ProviderGateway` falso (WA-5)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.notification_service import NotificationService
from application.outbound_message_service import OutboundMessageService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.enums import OutboxMessageStatus
from infrastructure.persistence.sqlite_outbox_repository import SqliteWhatsAppOutboxRepository
from infrastructure.webhooks.outbound_dispatcher import OutboundDispatcher


class _FakeProviderGateway:
    def __init__(self, *, should_fail=False):
        self.text_calls = []
        self._should_fail = should_fail

    async def send_text(self, *, to, body):
        if self._should_fail:
            raise RuntimeError("Meta API no disponible")
        self.text_calls.append((to, body))
        return {"ok": True}


class _FakeRoot:
    def __init__(self, conn, *, provider_gateway=None):
        self.outbox = SqliteWhatsAppOutboxRepository(conn)
        self.provider_gateway = provider_gateway or _FakeProviderGateway()
        self.outbound_message_service = OutboundMessageService(self)
        self.outbound_dispatcher = OutboundDispatcher(self)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestNotifyOrderReady:
    def test_sends_and_reports_success(self, conn):
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        message = _run(service.notify_order_ready(phone="+525512345678", folio="F-001", branch_name="Centro"))

        assert message.status == OutboxMessageStatus.SENT
        assert gateway.text_calls[0][0] == "+525512345678"
        assert "F-001" in gateway.text_calls[0][1]
        assert "Centro" in gateway.text_calls[0][1]

    def test_retrying_the_same_notification_does_not_send_twice(self, conn):
        """El caso real de WA-18: el ERP reintenta la misma notificación
        (p. ej. timeout de su lado, aunque el mensaje sí se haya
        encolado/enviado) — no debe duplicarse en la cola."""
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        first = _run(service.notify_order_ready(phone="+525512345678", folio="F-001"))
        second = _run(service.notify_order_ready(phone="+525512345678", folio="F-001"))

        assert first.id == second.id
        assert len(gateway.text_calls) == 1

    def test_different_folio_is_a_different_notification(self, conn):
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        first = _run(service.notify_order_ready(phone="+525512345678", folio="F-001"))
        second = _run(service.notify_order_ready(phone="+525512345678", folio="F-002"))

        assert first.id != second.id

    def test_gateway_failure_leaves_message_pending_for_retry(self, conn):
        gateway = _FakeProviderGateway(should_fail=True)
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        message = _run(service.notify_order_ready(phone="+525512345678", folio="F-001"))

        assert message.status == OutboxMessageStatus.PENDING
        assert message.next_retry_at is not None


class TestNotifyAdvanceRequired:
    def test_includes_amount_in_body(self, conn):
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        _run(service.notify_advance_required(phone="+525512345678", folio="F-001", amount=150.5))

        assert "150.50" in gateway.text_calls[0][1]


class TestNotifyQuoteReady:
    def test_includes_total_in_body(self, conn):
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        _run(service.notify_quote_ready(phone="+525512345678", folio="C-001", total=980.0))

        assert "980.00" in gateway.text_calls[0][1]


class TestSendCustom:
    def test_sends_free_text_message(self, conn):
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        message = _run(service.send_custom(phone="+525512345678", message="Hola, mensaje libre"))

        assert message.status == OutboxMessageStatus.SENT
        assert gateway.text_calls[0] == ("+525512345678", "Hola, mensaje libre")

    def test_two_calls_with_the_same_text_both_send(self, conn):
        """A diferencia de las notificaciones con folio, un mensaje libre
        no tiene `operation_id` — cada llamada es independiente."""
        gateway = _FakeProviderGateway()
        service = NotificationService(_FakeRoot(conn, provider_gateway=gateway))

        first = _run(service.send_custom(phone="+525512345678", message="Hola"))
        second = _run(service.send_custom(phone="+525512345678", message="Hola"))

        assert first.id != second.id
        assert len(gateway.text_calls) == 2
