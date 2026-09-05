# tests/test_outbound_message_service.py — WA-17
from __future__ import annotations

import sqlite3

import pytest

from application.outbound_message_service import OutboundMessageService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from infrastructure.persistence.sqlite_outbox_repository import SqliteWhatsAppOutboxRepository


class _FakeRoot:
    def __init__(self, conn):
        self.outbox = SqliteWhatsAppOutboxRepository(conn)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def service(conn):
    return OutboundMessageService(_FakeRoot(conn))


class TestEnqueueText:
    def test_enqueues_a_pending_message(self, service):
        message = service.enqueue_text(destination_phone="+525512345678", body="Hola")
        assert message.status.value == "PENDING"

    def test_same_operation_id_returns_the_same_message(self, service):
        """El caso real de WA-17: el llamador (p. ej. WA-18/Notificaciones)
        reintenta encolar la misma operación de negocio — no debe duplicar
        el mensaje en la cola."""
        first = service.enqueue_text(
            destination_phone="+525512345678", body="Tu pedido está listo", operation_id="notify-F001",
        )
        second = service.enqueue_text(
            destination_phone="+525512345678", body="Tu pedido está listo", operation_id="notify-F001",
        )
        assert first.id == second.id

    def test_different_operation_id_creates_a_new_message(self, service):
        first = service.enqueue_text(destination_phone="+525512345678", body="msg 1", operation_id="op-1")
        second = service.enqueue_text(destination_phone="+525512345678", body="msg 2", operation_id="op-2")
        assert first.id != second.id

    def test_without_operation_id_each_call_creates_a_new_message(self, service):
        first = service.enqueue_text(destination_phone="+525512345678", body="Hola")
        second = service.enqueue_text(destination_phone="+525512345678", body="Hola")
        assert first.id != second.id


class TestEnqueueTemplate:
    def test_enqueues_a_pending_template_message(self, service):
        message = service.enqueue_template(
            destination_phone="+525512345678", template_name="pedido_listo", parameters={"folio": "F-001"},
        )
        assert message.status.value == "PENDING"
        assert message.template_name == "pedido_listo"

    def test_same_operation_id_is_deduplicated(self, service):
        first = service.enqueue_template(
            destination_phone="+525512345678", template_name="pedido_listo", operation_id="tmpl-1",
        )
        second = service.enqueue_template(
            destination_phone="+525512345678", template_name="pedido_listo", operation_id="tmpl-1",
        )
        assert first.id == second.id
