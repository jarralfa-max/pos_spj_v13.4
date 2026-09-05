# tests/test_sqlite_order_draft_and_idempotency_repositories.py — WA-10
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.business_operation import BusinessOperationIdempotencyRecord
from domain.whatsapp.entities.order_draft import OrderDraft
from domain.whatsapp.enums import DeliveryMethod, IdempotencyStatus, OrderDraftStatus
from infrastructure.persistence.sqlite_idempotency_repository import SqliteWhatsAppIdempotencyRepository
from infrastructure.persistence.sqlite_order_draft_repository import SqliteWhatsAppOrderDraftRepository


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


class TestSqliteWhatsAppOrderDraftRepository:
    def test_save_and_get_by_id_round_trips_lines(self, conn):
        repo = SqliteWhatsAppOrderDraftRepository(conn)
        draft = OrderDraft.start(conversation_id="conv-1", branch_id="branch-1")
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        draft.set_delivery_method(DeliveryMethod.PICKUP)
        repo.save(draft)

        fetched = repo.get_by_id(draft.id)
        assert len(fetched.lines) == 1
        assert fetched.lines[0].product_name == "Bistec"
        assert fetched.delivery_method == DeliveryMethod.PICKUP
        assert fetched.total == 360.0

    def test_save_twice_replaces_lines_not_duplicates(self, conn):
        repo = SqliteWhatsAppOrderDraftRepository(conn)
        draft = OrderDraft.start(conversation_id="conv-1")
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        repo.save(draft)
        draft.add_line(product_external_id="p2", product_name="Costilla", quantity=1, unit="kg", unit_price=90.0)
        repo.save(draft)

        fetched = repo.get_by_id(draft.id)
        assert len(fetched.lines) == 2

    def test_get_active_for_conversation_ignores_confirmed(self, conn):
        repo = SqliteWhatsAppOrderDraftRepository(conn)
        confirmed = OrderDraft.start(conversation_id="conv-1")
        confirmed.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        confirmed.confirm()
        repo.save(confirmed)

        active = OrderDraft.start(conversation_id="conv-1")
        repo.save(active)

        fetched = repo.get_active_for_conversation("conv-1")
        assert fetched.id == active.id

    def test_get_by_id_missing_returns_none(self, conn):
        repo = SqliteWhatsAppOrderDraftRepository(conn)
        assert repo.get_by_id("missing") is None


class TestSqliteWhatsAppIdempotencyRepository:
    def test_save_and_get_by_fingerprint(self, conn):
        repo = SqliteWhatsAppIdempotencyRepository(conn)
        record = BusinessOperationIdempotencyRecord.start(
            operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT", aggregate_id="d1", fingerprint="fp-1"
        )
        repo.save(record)
        fetched = repo.get_by_fingerprint("fp-1")
        assert fetched.status == IdempotencyStatus.PENDING

    def test_save_twice_upserts_completion(self, conn):
        repo = SqliteWhatsAppIdempotencyRepository(conn)
        record = BusinessOperationIdempotencyRecord.start(
            operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT", aggregate_id="d1", fingerprint="fp-2"
        )
        repo.save(record)
        record.complete("order-1")
        repo.save(record)

        fetched = repo.get_by_fingerprint("fp-2")
        assert fetched.status == IdempotencyStatus.COMPLETED
        assert fetched.result_reference == "order-1"

    def test_get_by_fingerprint_missing_returns_none(self, conn):
        repo = SqliteWhatsAppIdempotencyRepository(conn)
        assert repo.get_by_fingerprint("missing") is None

    def test_fingerprint_is_unique(self, conn):
        repo = SqliteWhatsAppIdempotencyRepository(conn)
        first = BusinessOperationIdempotencyRecord.start(
            operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT", aggregate_id="d1", fingerprint="fp-dup"
        )
        repo.save(first)
        second = BusinessOperationIdempotencyRecord.start(
            operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT", aggregate_id="d2", fingerprint="fp-dup"
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(second)
