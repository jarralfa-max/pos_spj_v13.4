# tests/test_sqlite_quote_draft_repository.py — WA-11
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.quote_draft import QuoteDraft
from domain.whatsapp.enums import QuoteDraftStatus
from infrastructure.persistence.sqlite_quote_draft_repository import SqliteWhatsAppQuoteDraftRepository


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


class TestSqliteWhatsAppQuoteDraftRepository:
    def test_save_and_get_by_id_round_trips_lines_and_folio(self, conn):
        repo = SqliteWhatsAppQuoteDraftRepository(conn)
        draft = QuoteDraft.start(conversation_id="conv-1", branch_id="branch-1")
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        draft.mark_created(quote_external_id="q1", folio="COT-001")
        repo.save(draft)

        fetched = repo.get_by_id(draft.id)
        assert fetched.status == QuoteDraftStatus.CREATED
        assert fetched.folio == "COT-001"
        assert fetched.quote_external_id == "q1"
        assert len(fetched.lines) == 1
        assert fetched.total == 360.0

    def test_get_active_for_conversation_ignores_accepted(self, conn):
        repo = SqliteWhatsAppQuoteDraftRepository(conn)
        accepted = QuoteDraft.start(conversation_id="conv-1")
        accepted.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        accepted.mark_created(quote_external_id="q1")
        accepted.accept()
        repo.save(accepted)

        active = QuoteDraft.start(conversation_id="conv-1")
        repo.save(active)

        fetched = repo.get_active_for_conversation("conv-1")
        assert fetched.id == active.id

    def test_save_twice_replaces_lines(self, conn):
        repo = SqliteWhatsAppQuoteDraftRepository(conn)
        draft = QuoteDraft.start(conversation_id="conv-1")
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        repo.save(draft)
        draft.add_line(product_external_id="p2", product_name="Costilla", quantity=1, unit="kg", unit_price=90.0)
        repo.save(draft)
        assert len(repo.get_by_id(draft.id).lines) == 2

    def test_get_by_id_missing_returns_none(self, conn):
        repo = SqliteWhatsAppQuoteDraftRepository(conn)
        assert repo.get_by_id("missing") is None
