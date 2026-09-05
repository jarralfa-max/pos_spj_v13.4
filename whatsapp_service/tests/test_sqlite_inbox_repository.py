# tests/test_sqlite_inbox_repository.py — WA-6
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.inbox_job import InboundMessageJob
from domain.whatsapp.enums import InboxStatus
from infrastructure.persistence.sqlite_inbox_repository import SqliteWhatsAppInboxRepository


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


class TestSqliteWhatsAppInboxRepository:
    def test_save_and_get_by_id(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        job = InboundMessageJob.create(message_id="msg-1")
        repo.save(job)
        fetched = repo.get_by_id(job.id)
        assert fetched.status == InboxStatus.PENDING

    def test_get_by_message_id(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        job = InboundMessageJob.create(message_id="msg-9")
        repo.save(job)
        assert repo.get_by_message_id("msg-9").id == job.id

    def test_save_twice_upserts_transition(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        job = InboundMessageJob.create(message_id="msg-1")
        repo.save(job)
        job.claim()
        repo.save(job)
        fetched = repo.get_by_id(job.id)
        assert fetched.status == InboxStatus.PROCESSING
        assert fetched.attempts == 1

    def test_claim_pending_returns_only_pending_and_retry(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        pending = InboundMessageJob.create(message_id="msg-pending")
        repo.save(pending)

        completed = InboundMessageJob.create(message_id="msg-done")
        completed.claim()
        completed.complete()
        repo.save(completed)

        claimed = repo.claim_pending()
        ids = {j.id for j in claimed}
        assert pending.id in ids
        assert completed.id not in ids

    def test_claim_pending_marks_processing_in_db(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        job = InboundMessageJob.create(message_id="msg-1")
        repo.save(job)
        repo.claim_pending()
        assert repo.get_by_id(job.id).status == InboxStatus.PROCESSING

    def test_claim_pending_respects_limit(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        for i in range(5):
            repo.save(InboundMessageJob.create(message_id=f"msg-{i}"))
        claimed = repo.claim_pending(limit=2)
        assert len(claimed) == 2

    def test_claim_pending_includes_retry_status(self, conn):
        repo = SqliteWhatsAppInboxRepository(conn)
        job = InboundMessageJob.create(message_id="msg-retry")
        job.claim()
        job.fail("x")
        job.schedule_retry()
        repo.save(job)
        claimed = repo.claim_pending()
        assert [j.id for j in claimed] == [job.id]
