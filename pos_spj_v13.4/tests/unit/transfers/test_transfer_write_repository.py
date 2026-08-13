"""INV-12 — TransferWriteRepository: the first production StockTransferRepository."""
from decimal import Decimal

import sqlite3

import pytest

from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.value_objects.transfer_node import TransferNode
from backend.infrastructure.db.repositories.transfers.transfer_write_repository import (
    TransferWriteRepository,
)
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_transfers_schema(c)
    c.commit()
    yield c
    c.close()


def _transfer(**overrides) -> StockTransfer:
    defaults = dict(
        transfer_number="TRF-2026-000001", transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.BRANCH, branch_id="b1"),
        destination_node=TransferNode(TransferNodeType.BRANCH, branch_id="b2"),
        requested_by_user_id="u1", operation_id="op-1",
        lines=[StockTransferLine(product_id="p1", unit_id="unit-kg",
                                 requested_quantity=Decimal("10"))])
    defaults.update(overrides)
    return StockTransfer(**defaults)


class TestSaveAndGet:
    def test_round_trips_header_and_lines(self, conn):
        repo = TransferWriteRepository(conn)
        transfer = _transfer()
        repo.save(transfer)
        conn.commit()

        loaded = repo.get(transfer.id)
        assert loaded is not None
        assert loaded.transfer_number == "TRF-2026-000001"
        assert loaded.status is TransferStatus.DRAFT
        assert loaded.origin_node.branch_id == "b1"
        assert loaded.destination_node.branch_id == "b2"
        assert len(loaded.lines) == 1
        assert loaded.lines[0].product_id == "p1"
        assert loaded.lines[0].requested_quantity == Decimal("10")

    def test_get_missing_transfer_returns_none(self, conn):
        assert TransferWriteRepository(conn).get("does-not-exist") is None

    def test_save_again_updates_status_and_lines(self, conn):
        repo = TransferWriteRepository(conn)
        transfer = _transfer()
        repo.save(transfer)
        conn.commit()
        transfer.submit()
        repo.save(transfer)
        conn.commit()

        loaded = repo.get(transfer.id)
        assert loaded.status is TransferStatus.PENDING_APPROVAL

    def test_duplicate_transfer_number_is_rejected_by_the_schema(self, conn):
        repo = TransferWriteRepository(conn)
        repo.save(_transfer())
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(_transfer(operation_id="op-2"))


class TestOperationIdempotency:
    def test_operation_exists_false_before_record_true_after(self, conn):
        repo = TransferWriteRepository(conn)
        transfer = _transfer()
        assert repo.operation_exists("op-1") is False
        repo.save(transfer)
        repo.record_operation(transfer_id=transfer.id, operation_id="op-1",
                              operation_type="TRANSFER_REQUEST_CREATE")
        assert repo.operation_exists("op-1") is True

    def test_record_operation_attributes_actor_to_the_requester(self, conn):
        repo = TransferWriteRepository(conn)
        transfer = _transfer(requested_by_user_id="requester-1")
        repo.save(transfer)
        repo.record_operation(transfer_id=transfer.id, operation_id="op-1",
                              operation_type="TRANSFER_REQUEST_CREATE")
        row = conn.execute(
            "SELECT actor_user_id FROM transfer_operations WHERE operation_id = ?",
            ("op-1",)).fetchone()
        assert row["actor_user_id"] == "requester-1"
