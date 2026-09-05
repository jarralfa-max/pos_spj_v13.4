# tests/test_inbox_worker.py — WA-6
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.composition_root import WhatsAppCompositionRoot
from domain.whatsapp.entities.inbox_job import InboundMessageJob
from domain.whatsapp.enums import InboxStatus
from infrastructure.webhooks.inbox_worker import MAX_ATTEMPTS, InboxWorker


@pytest.fixture()
def root():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    r = WhatsAppCompositionRoot(connection)
    yield r
    connection.close()


def _seed_job(root, **overrides) -> InboundMessageJob:
    job = InboundMessageJob.create(message_id=overrides.get("message_id", "msg-1"))
    root.inbox.save(job)
    return job


class TestInboxWorkerDefaultHandler:
    def test_run_once_completes_pending_jobs_with_noop_handler(self, root):
        job = _seed_job(root)
        worker = InboxWorker(root)
        claimed = asyncio.run(worker.run_once())
        assert claimed == 1
        assert root.inbox.get_by_id(job.id).status == InboxStatus.COMPLETED

    def test_run_once_returns_zero_when_queue_empty(self, root):
        worker = InboxWorker(root)
        assert asyncio.run(worker.run_once()) == 0


class TestInboxWorkerCustomHandler:
    def test_successful_handler_completes_job(self, root):
        job = _seed_job(root)
        calls = []

        async def handler(j):
            calls.append(j.id)

        worker = InboxWorker(root, handler=handler)
        asyncio.run(worker.run_once())
        assert calls == [job.id]
        assert root.inbox.get_by_id(job.id).status == InboxStatus.COMPLETED

    def test_failing_handler_schedules_retry_below_max_attempts(self, root):
        job = _seed_job(root)

        async def handler(j):
            raise RuntimeError("boom")

        worker = InboxWorker(root, handler=handler)
        asyncio.run(worker.run_once())
        fetched = root.inbox.get_by_id(job.id)
        assert fetched.status == InboxStatus.RETRY
        assert fetched.last_error == "boom"

    def test_failing_handler_moves_to_dead_letter_after_max_attempts(self, root):
        job = _seed_job(root)

        async def handler(j):
            raise RuntimeError("boom")

        worker = InboxWorker(root, handler=handler)
        for _ in range(MAX_ATTEMPTS):
            asyncio.run(worker.run_once())
            fetched = root.inbox.get_by_id(job.id)
            if fetched.status == InboxStatus.RETRY:
                # Vuelve a quedar reclamable — el siguiente run_once la toma de nuevo.
                continue
        final = root.inbox.get_by_id(job.id)
        assert final.status == InboxStatus.DEAD_LETTER
        assert final.attempts == MAX_ATTEMPTS

    def test_run_once_respects_limit(self, root):
        for i in range(5):
            _seed_job(root, message_id=f"msg-{i}")
        worker = InboxWorker(root)
        claimed = asyncio.run(worker.run_once(limit=2))
        assert claimed == 2
