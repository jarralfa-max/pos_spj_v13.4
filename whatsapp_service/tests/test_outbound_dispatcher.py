# tests/test_outbound_dispatcher.py — WA-17
"""`OutboundDispatcher` contra un `outbox` repository SQLite real (WA-3/
WA-17) y un `ProviderGateway` falso (el contrato de WA-5, no su
implementación real)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.outbound_message_service import OutboundMessageService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.enums import OutboxMessageStatus
from infrastructure.persistence.sqlite_outbox_repository import SqliteWhatsAppOutboxRepository
from infrastructure.webhooks.outbound_dispatcher import OutboundDispatcher


class _FakeProviderGateway:
    def __init__(self, *, fail_times=0):
        self.text_calls = []
        self.template_calls = []
        self._fail_times = fail_times

    async def send_text(self, *, to, body):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("Meta API timeout")
        self.text_calls.append((to, body))
        return {"ok": True}

    async def send_template(self, *, to, template_name, language, parameters):
        self.template_calls.append((to, template_name, language, parameters))
        return {"ok": True}


class _FakeRoot:
    def __init__(self, conn, *, provider_gateway=None):
        self.outbox = SqliteWhatsAppOutboxRepository(conn)
        self.provider_gateway = provider_gateway or _FakeProviderGateway()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestRunOnce:
    def test_dispatches_a_pending_text_message(self, conn):
        gateway = _FakeProviderGateway()
        root = _FakeRoot(conn, provider_gateway=gateway)
        OutboundMessageService(root).enqueue_text(destination_phone="+525512345678", body="Hola")

        claimed = _run(OutboundDispatcher(root).run_once())

        assert claimed == 1
        assert gateway.text_calls == [("+525512345678", "Hola")]

    def test_marks_message_sent_after_successful_dispatch(self, conn):
        root = _FakeRoot(conn)
        message = OutboundMessageService(root).enqueue_text(destination_phone="+525512345678", body="Hola")

        _run(OutboundDispatcher(root).run_once())

        fetched = root.outbox.get_by_id(message.id)
        assert fetched.status == OutboxMessageStatus.SENT

    def test_dispatches_a_template_message(self, conn):
        gateway = _FakeProviderGateway()
        root = _FakeRoot(conn, provider_gateway=gateway)
        OutboundMessageService(root).enqueue_template(
            destination_phone="+525512345678", template_name="pedido_listo", parameters={"folio": "F-001"},
        )

        _run(OutboundDispatcher(root).run_once())

        assert gateway.template_calls == [("+525512345678", "pedido_listo", "es_MX", {"folio": "F-001"})]

    def test_gateway_failure_schedules_retry_not_lost(self, conn):
        gateway = _FakeProviderGateway(fail_times=1)
        root = _FakeRoot(conn, provider_gateway=gateway)
        message = OutboundMessageService(root).enqueue_text(destination_phone="+525512345678", body="Hola")

        _run(OutboundDispatcher(root).run_once())

        fetched = root.outbox.get_by_id(message.id)
        assert fetched.status == OutboxMessageStatus.PENDING
        assert fetched.attempts == 1
        assert fetched.next_retry_at is not None

    def test_does_not_redispatch_a_message_not_yet_due_for_retry(self, conn):
        """El caso real de WA-17: un fallo agenda un reintento futuro — un
        `run_once()` inmediato después NO debe reintentar todavía."""
        gateway = _FakeProviderGateway(fail_times=1)
        root = _FakeRoot(conn, provider_gateway=gateway)
        OutboundMessageService(root).enqueue_text(destination_phone="+525512345678", body="Hola")

        first_run = _run(OutboundDispatcher(root).run_once())
        second_run = _run(OutboundDispatcher(root).run_once())

        assert first_run == 1
        assert second_run == 0

    def test_processes_multiple_pending_messages(self, conn):
        gateway = _FakeProviderGateway()
        root = _FakeRoot(conn, provider_gateway=gateway)
        service = OutboundMessageService(root)
        service.enqueue_text(destination_phone="+525511111111", body="msg 1")
        service.enqueue_text(destination_phone="+525522222222", body="msg 2")

        claimed = _run(OutboundDispatcher(root).run_once())

        assert claimed == 2
        assert len(gateway.text_calls) == 2

    def test_unknown_payload_kind_is_treated_as_a_dispatch_failure(self, conn):
        from domain.whatsapp.entities.outbox_message import OutboxMessage as _OutboxMessage

        root = _FakeRoot(conn)
        # Construye directamente (no vía enqueue_text/enqueue_template,
        # que no permiten un `kind` distinto de "text"/"template") para
        # simular un payload corrupto/de un origen desconocido.
        message = _OutboxMessage._new(destination_phone="+525512345678", payload={"kind": "unknown"})
        root.outbox.save(message)

        _run(OutboundDispatcher(root).run_once())

        fetched = root.outbox.get_by_id(message.id)
        assert fetched.status == OutboxMessageStatus.PENDING
        assert fetched.last_error is not None


class TestDispatchNow:
    def test_dispatches_the_specific_message_immediately(self, conn):
        gateway = _FakeProviderGateway()
        root = _FakeRoot(conn, provider_gateway=gateway)
        message = OutboundMessageService(root).enqueue_text(destination_phone="+525512345678", body="Hola")

        result = _run(OutboundDispatcher(root).dispatch_now(message.id))

        assert result.status == OutboxMessageStatus.SENT
        assert gateway.text_calls == [("+525512345678", "Hola")]

    def test_only_dispatches_the_requested_message_not_others_pending(self, conn):
        gateway = _FakeProviderGateway()
        root = _FakeRoot(conn, provider_gateway=gateway)
        service = OutboundMessageService(root)
        target = service.enqueue_text(destination_phone="+525511111111", body="target")
        other = service.enqueue_text(destination_phone="+525522222222", body="other")

        _run(OutboundDispatcher(root).dispatch_now(target.id))

        assert gateway.text_calls == [("+525511111111", "target")]
        assert root.outbox.get_by_id(other.id).status == OutboxMessageStatus.PENDING

    def test_raises_for_unknown_message_id(self, conn):
        root = _FakeRoot(conn)
        with pytest.raises(ValueError):
            _run(OutboundDispatcher(root).dispatch_now("does-not-exist"))

    def test_does_not_redispatch_a_message_not_yet_due(self, conn):
        gateway = _FakeProviderGateway(fail_times=1)
        root = _FakeRoot(conn, provider_gateway=gateway)
        message = OutboundMessageService(root).enqueue_text(destination_phone="+525512345678", body="Hola")
        _run(OutboundDispatcher(root).dispatch_now(message.id))  # falla, agenda reintento futuro

        result = _run(OutboundDispatcher(root).dispatch_now(message.id))

        assert result.status == OutboxMessageStatus.PENDING
        assert len(gateway.text_calls) == 0  # nunca llegó a reintentar antes de tiempo
