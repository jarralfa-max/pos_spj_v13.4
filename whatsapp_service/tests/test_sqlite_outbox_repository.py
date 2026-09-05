# tests/test_sqlite_outbox_repository.py — WA-17
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.outbox_message import OutboxMessage
from domain.whatsapp.enums import OutboxMessageStatus
from infrastructure.persistence.sqlite_outbox_repository import SqliteWhatsAppOutboxRepository


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def repo(conn):
    return SqliteWhatsAppOutboxRepository(conn)


class TestRoundTrip:
    def test_save_and_get_by_id(self, repo):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        repo.save(message)

        fetched = repo.get_by_id(message.id)
        assert fetched is not None
        assert fetched.destination_phone == "+525512345678"
        assert fetched.payload == {"kind": "text", "body": "Hola"}
        assert fetched.status == OutboxMessageStatus.PENDING

    def test_get_by_operation_id(self, repo):
        message = OutboxMessage.enqueue_text(
            destination_phone="+525512345678", body="Hola", operation_id="op-1",
        )
        repo.save(message)

        fetched = repo.get_by_operation_id("op-1")
        assert fetched is not None
        assert fetched.id == message.id

    def test_get_by_operation_id_missing_returns_none(self, repo):
        assert repo.get_by_operation_id("does-not-exist") is None

    def test_update_persists_status_transition(self, repo):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        repo.save(message)
        message.claim()
        message.mark_sent()
        repo.save(message)

        fetched = repo.get_by_id(message.id)
        assert fetched.status == OutboxMessageStatus.SENT
        assert fetched.attempts == 1


class TestClaimDue:
    def test_claims_pending_messages_and_bumps_attempts(self, repo):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        repo.save(message)

        claimed = repo.claim_due(limit=10)
        assert len(claimed) == 1
        assert claimed[0].attempts == 1

        # Persistido, no solo en memoria.
        fetched = repo.get_by_id(message.id)
        assert fetched.attempts == 1

    def test_does_not_claim_a_message_scheduled_for_the_future(self, conn, repo):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        repo.save(message)
        message.claim()
        message.mark_failed("timeout")  # next_retry_at en el futuro
        repo.save(message)

        assert repo.claim_due(limit=10) == []

    def test_claims_a_message_whose_retry_window_has_passed(self, conn, repo):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        repo.save(message)
        message.claim()
        message.mark_failed("timeout")
        message.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        repo.save(message)

        claimed = repo.claim_due(limit=10)
        assert len(claimed) == 1
        assert claimed[0].id == message.id

    def test_does_not_claim_sent_or_dead_letter_messages(self, repo):
        sent = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        sent.claim()
        sent.mark_sent()
        repo.save(sent)

        assert repo.claim_due(limit=10) == []

    def test_respects_limit(self, repo):
        for _ in range(3):
            repo.save(OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola"))

        claimed = repo.claim_due(limit=2)
        assert len(claimed) == 2
