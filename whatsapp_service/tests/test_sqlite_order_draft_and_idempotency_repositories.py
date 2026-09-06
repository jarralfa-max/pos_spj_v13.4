# tests/test_sqlite_order_draft_and_idempotency_repositories.py — WA-10
from __future__ import annotations

import sqlite3
from decimal import Decimal

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


class TestMoneyIsStoredAsDecimalText:
    """§9: el dinero se persiste como TEXT decimal, nunca como REAL.

    Las columnas eran `quantity REAL` / `unit_price REAL`. Un REAL no puede
    representar 0.1 exactamente, así que el valor recuperado no era el guardado.
    """

    def test_round_trip_preserves_the_exact_decimal(self, conn):
        repository = SqliteWhatsAppOrderDraftRepository(conn)
        draft = OrderDraft.start(conversation_id="C-money")
        draft.add_line(product_external_id="P1", product_name="Arrachera",
                       quantity="1.5", unit="kg", unit_price="0.1")
        repository.save(draft)

        restored = repository.get_by_id(draft.id)
        line = restored.lines[0]
        assert line.unit_price == Decimal("0.1")
        assert line.quantity == Decimal("1.5")
        assert isinstance(line.unit_price, Decimal)
        assert str(line.unit_price) == "0.1"

    def test_columns_are_text_not_real(self, conn):
        for table in ("whatsapp_order_draft_lines", "whatsapp_quote_draft_lines"):
            types = {
                row[1]: row[2]
                for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            assert types["unit_price"] == "TEXT", f"{table}.unit_price debe ser TEXT"
            assert types["quantity"] == "TEXT", f"{table}.quantity debe ser TEXT"

    def test_stored_value_is_the_literal_decimal_string(self, conn):
        repository = SqliteWhatsAppOrderDraftRepository(conn)
        draft = OrderDraft.start(conversation_id="C-literal")
        draft.add_line(product_external_id="P2", product_name="Chorizo",
                       quantity="2", unit="kg", unit_price="19.99")
        repository.save(draft)

        stored = conn.execute(
            "SELECT quantity, unit_price FROM whatsapp_order_draft_lines WHERE draft_id=?",
            (draft.id,),
        ).fetchone()
        assert stored == ("2", "19.99")
