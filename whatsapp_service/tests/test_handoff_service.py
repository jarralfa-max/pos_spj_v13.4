# tests/test_handoff_service.py — WA-16
"""`HandoffCoordinator` contra un `handoff_requests` repository SQLite real
(WA-16) y `staff_directory`/`provider_gateway`/`conversation_engine`
falsos (los contratos de WA-9/WA-5/WA-7, no sus implementaciones)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.handoff_service import HandoffCoordinator
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.enums import ConversationState
from infrastructure.persistence.sqlite_handoff_request_repository import (
    SqliteWhatsAppHandoffRequestRepository,
)


class _FakeStaffDirectory:
    def __init__(self, phones_by_role=None):
        self._phones_by_role = phones_by_role or {}
        self.calls = []

    async def get_staff_phones(self, branch_id, *, role=""):
        self.calls.append((branch_id, role))
        return list(self._phones_by_role.get(role, []))


class _FakeProviderGateway:
    def __init__(self):
        self.sent = []

    async def send_text(self, *, to, body):
        self.sent.append((to, body))
        return {"ok": True}


class _FakeConversationEngine:
    def __init__(self):
        self.calls = []

    def handle_signal(self, conversation, signal):
        self.calls.append((conversation.id, signal))
        conversation.state = ConversationState.HANDOFF_REQUESTED
        return conversation


class _FakeRoot:
    def __init__(self, conn, *, staff_directory=None, provider_gateway=None, conversation_engine=None):
        self.handoff_requests = SqliteWhatsAppHandoffRequestRepository(conn)
        self.staff_directory = staff_directory or _FakeStaffDirectory()
        self.provider_gateway = provider_gateway or _FakeProviderGateway()
        self.conversation_engine = conversation_engine or _FakeConversationEngine()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


def _conversation():
    return WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1", branch_id="branch-1")


class TestRequestHandoff:
    def test_notifies_manager_first_when_available(self, conn):
        staff = _FakeStaffDirectory(phones_by_role={"gerente": ["+525511111111"]})
        gateway = _FakeProviderGateway()
        service = HandoffCoordinator(_FakeRoot(conn, staff_directory=staff, provider_gateway=gateway))

        request = _run(service.request_handoff(
            _conversation(), customer_phone="+525599999999", reason="No entendió", branch_id="branch-1",
        ))

        assert request.assigned_to_phone == "+525511111111"
        staff_notification = [call for call in gateway.sent if call[0] == "+525511111111"]
        assert len(staff_notification) == 1
        customer_notification = [call for call in gateway.sent if call[0] == "+525599999999"]
        assert len(customer_notification) == 1

    def test_falls_back_to_any_staff_when_no_manager(self, conn):
        staff = _FakeStaffDirectory(phones_by_role={"": ["+525522222222"]})
        service = HandoffCoordinator(_FakeRoot(conn, staff_directory=staff))

        request = _run(service.request_handoff(
            _conversation(), customer_phone="+525599999999", reason="motivo", branch_id="branch-1",
        ))

        assert request.assigned_to_phone == "+525522222222"
        assert staff.calls == [("branch-1", "gerente"), ("branch-1", "")]

    def test_second_request_for_same_conversation_does_not_notify_again(self, conn):
        """El caso real de WA-16: el cliente insiste "hablar con alguien"
        varias veces mientras espera — no debe re-notificar al staff cada
        vez."""
        staff = _FakeStaffDirectory(phones_by_role={"gerente": ["+525511111111"]})
        gateway = _FakeProviderGateway()
        root = _FakeRoot(conn, staff_directory=staff, provider_gateway=gateway)
        service = HandoffCoordinator(root)
        conversation = _conversation()

        first = _run(service.request_handoff(
            conversation, customer_phone="+525599999999", reason="motivo", branch_id="branch-1",
        ))
        second = _run(service.request_handoff(
            conversation, customer_phone="+525599999999", reason="otra vez", branch_id="branch-1",
        ))

        assert first.id == second.id
        assert len(gateway.sent) == 2  # 1 staff + 1 cliente, no 4

    def test_transitions_conversation_via_conversation_engine(self, conn):
        engine = _FakeConversationEngine()
        service = HandoffCoordinator(_FakeRoot(conn, conversation_engine=engine))
        conversation = _conversation()

        _run(service.request_handoff(conversation, customer_phone="+525599999999", reason="motivo"))

        assert len(engine.calls) == 1
        assert conversation.state == ConversationState.HANDOFF_REQUESTED

    def test_no_staff_available_still_notifies_customer_and_leaves_unassigned(self, conn):
        gateway = _FakeProviderGateway()
        service = HandoffCoordinator(_FakeRoot(conn, provider_gateway=gateway))

        request = _run(service.request_handoff(
            _conversation(), customer_phone="+525599999999", reason="motivo",
        ))

        assert request.assigned_to_phone is None
        assert len(gateway.sent) == 1
        assert gateway.sent[0][0] == "+525599999999"


class TestResolve:
    def test_resolve_marks_request_resolved(self, conn):
        service = HandoffCoordinator(_FakeRoot(conn))
        conversation = _conversation()
        request = _run(service.request_handoff(conversation, customer_phone="+525599999999", reason="motivo"))

        resolved = service.resolve(request.id)

        assert resolved.status.value == "RESOLVED"

    def test_resolve_unknown_request_raises(self, conn):
        service = HandoffCoordinator(_FakeRoot(conn))
        with pytest.raises(ValueError):
            service.resolve("does-not-exist")
