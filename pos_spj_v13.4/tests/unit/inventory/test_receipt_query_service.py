"""ReceiptQueryService.status_for_document — narrow, indexed single-lookup
counterpart to list_recent() (§15), added so other bounded contexts (e.g.
Procurement, via InventoryReceiptStatusPort) can ask whether *their* document
has posted into inventory yet without pulling the whole recent ledger window.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.inventory.queries.receipt_query_service import (
    ReceiptQueryService,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def inv_conn():
    conn = sqlite3.connect(":memory:")
    create_inventory_schema(conn)
    conn.execute(
        "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
        " source_module, source_document_type, source_document_id, operation_id,"
        " created_by_user_id, status, occurred_at) VALUES"
        " ('m1','PURCHASE_RECEIPT','br1','wh1','PROCUREMENT','PURCHASE_ORDER','po1',"
        " 'op-m1','u1','POSTED','2026-01-01T10:00:00+00:00')")
    # A later, superseding movement for the same document — most recent wins.
    conn.execute(
        "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
        " source_module, source_document_type, source_document_id, operation_id,"
        " created_by_user_id, status, occurred_at) VALUES"
        " ('m2','PURCHASE_RECEIPT','br1','wh1','PROCUREMENT','PURCHASE_ORDER','po1',"
        " 'op-m2','u1','POSTED','2026-01-02T10:00:00+00:00')")
    # Unrelated document, and a non-receipt movement type — must never match.
    conn.execute(
        "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
        " source_module, source_document_type, source_document_id, operation_id,"
        " created_by_user_id, status, occurred_at) VALUES"
        " ('m3','ADJUSTMENT','br1','wh1','INVENTORY','ADJUSTMENT','po1',"
        " 'op-m3','u1','POSTED','2026-01-03T10:00:00+00:00')")
    yield conn
    conn.close()


def test_status_for_document_returns_most_recent_receipt(inv_conn):
    service = ReceiptQueryService(inv_conn)
    row = service.status_for_document("po1")
    assert row is not None
    assert row["id"] == "m2"
    assert row["status"] == "POSTED"
    assert row["occurred_at"] == "2026-01-02T10:00:00+00:00"


def test_status_for_document_none_for_unknown_document(inv_conn):
    service = ReceiptQueryService(inv_conn)
    assert service.status_for_document("does-not-exist") is None


def test_status_for_document_ignores_non_receipt_movement_types(inv_conn):
    """A document id that only appears on an ADJUSTMENT movement (never an
    inbound receipt type) must not be reported as received."""
    conn = sqlite3.connect(":memory:")
    create_inventory_schema(conn)
    conn.execute(
        "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
        " source_module, source_document_type, source_document_id, operation_id,"
        " created_by_user_id, status, occurred_at) VALUES"
        " ('m1','ADJUSTMENT','br1','wh1','INVENTORY','ADJUSTMENT','doc-x',"
        " 'op-m1','u1','POSTED','2026-01-01T10:00:00+00:00')")
    service = ReceiptQueryService(conn)
    assert service.status_for_document("doc-x") is None
    conn.close()
