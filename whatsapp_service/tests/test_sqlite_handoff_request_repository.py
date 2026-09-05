# tests/test_sqlite_handoff_request_repository.py — WA-16
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.handoff_request import HandoffRequest
from domain.whatsapp.enums import HandoffStatus
from infrastructure.persistence.sqlite_handoff_request_repository import (
    SqliteWhatsAppHandoffRequestRepository,
)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def repo(conn):
    return SqliteWhatsAppHandoffRequestRepository(conn)


class TestRoundTrip:
    def test_save_and_get_by_id(self, repo):
        request = HandoffRequest.open(conversation_id="conv-1", reason="Cliente confundido", branch_id="branch-1")
        repo.save(request)

        fetched = repo.get_by_id(request.id)
        assert fetched is not None
        assert fetched.reason == "Cliente confundido"
        assert fetched.branch_id == "branch-1"
        assert fetched.status == HandoffStatus.OPEN

    def test_update_persists_assignment(self, repo):
        request = HandoffRequest.open(conversation_id="conv-1", reason="motivo")
        repo.save(request)
        request.assign("+525500000000")
        repo.save(request)

        fetched = repo.get_by_id(request.id)
        assert fetched.status == HandoffStatus.ASSIGNED
        assert fetched.assigned_to_phone == "+525500000000"

    def test_get_open_for_conversation_ignores_resolved(self, repo):
        resolved = HandoffRequest.open(conversation_id="conv-1", reason="ya resuelto")
        resolved.resolve()
        repo.save(resolved)

        assert repo.get_open_for_conversation("conv-1") is None

    def test_get_open_for_conversation_returns_open_request(self, repo):
        request = HandoffRequest.open(conversation_id="conv-1", reason="motivo")
        repo.save(request)

        fetched = repo.get_open_for_conversation("conv-1")
        assert fetched is not None
        assert fetched.id == request.id

    def test_get_by_id_missing_returns_none(self, repo):
        assert repo.get_by_id("does-not-exist") is None
