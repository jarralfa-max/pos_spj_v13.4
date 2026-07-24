"""TRF-23 clean-bootstrap smoke test from canonical DDL to workspace query."""
import sqlite3

from backend.infrastructure.db.repositories.transfers import (
    TransferWorkspaceQueryRepository,
)
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema
from backend.shared.ids import new_uuid


def test_clean_database_exposes_a_canonical_transfer_in_workspace():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(connection)
    transfer_id, operation_id = new_uuid(), new_uuid()
    connection.execute(
        """INSERT INTO stock_transfers (
            id, transfer_number, transfer_type, source_channel, source_module,
            origin_node_type, origin_branch_id, destination_node_type,
            destination_branch_id, requested_by_user_id, priority, status,
            transport_required, cold_chain_required, blind_receipt_required,
            operation_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?)""",
        (transfer_id, "TRF-2026-000001", "REPLENISHMENT", "DESKTOP", "transfers",
         "BRANCH", new_uuid(), "BRANCH", new_uuid(), new_uuid(), "NORMAL",
         "PENDING_APPROVAL", operation_id, "2026-07-24T10:00:00+00:00",
         "2026-07-24T10:00:00+00:00"),
    )

    page = TransferWorkspaceQueryRepository(connection).page(
        page_id="transfers_approvals")

    assert len(page.rows) == 1
    assert page.rows[0].entity_id == transfer_id
    assert page.rows[0].reference == "TRF-2026-000001"

