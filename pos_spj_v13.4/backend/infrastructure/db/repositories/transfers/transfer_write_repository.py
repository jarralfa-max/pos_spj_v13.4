"""Production ``StockTransferRepository`` — the first write-side Transfers
repository (INV-12 vertical slice: Create Transfer Request).

Plain-connection style, matching the existing read-only
``TransferWorkspaceQueryRepository`` in ``transfer_query_repository.py`` — raw
``connection.execute(sql, params)``, no ORM. See
``backend/infrastructure/db/schema/transfers_schema.py`` for the exact DDL.

Two schema/entity gaps this repository papers over, both flagged rather than
silently patched:

- ``stock_transfers.source_module`` is ``NOT NULL`` but ``StockTransfer`` has
  no such field; manually-created requests are stamped ``"transfers"``. A
  later phase modelling system-originated transfers (replenishment
  suggestions, etc.) may want this to vary by ``source_channel``.
- ``transfer_operations.actor_user_id`` is ``NOT NULL`` but
  ``StockTransferRepository.record_operation`` (the Protocol) does not carry
  an actor. For every use case wired so far (Create only), the actor **is**
  the transfer's ``requested_by_user_id``, so ``record_operation`` reads it
  back from the just-saved row. A later phase wiring Edit/Submit/Approve/Reject
  (whose actors differ from the requester) must reconsider this.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.value_objects.transfer_node import TransferNode
from backend.shared.ids import new_uuid

_LINE_NUMERIC_COLUMNS = (
    "requested_quantity", "requested_weight", "approved_quantity", "approved_weight",
    "reserved_quantity", "reserved_weight", "picked_quantity", "picked_weight",
    "dispatched_quantity", "dispatched_weight", "received_quantity", "received_weight",
    "accepted_quantity", "accepted_weight", "rejected_quantity", "rejected_weight", "pieces",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TransferWriteRepository:
    """Production ``StockTransferRepository`` over ``stock_transfers`` /
    ``stock_transfer_lines`` / ``transfer_operations``."""

    def __init__(self, connection) -> None:
        self._db = connection

    # ── reads ────────────────────────────────────────────────────────────────
    def get(self, transfer_id: str) -> StockTransfer | None:
        row = self._db.execute(
            "SELECT * FROM stock_transfers WHERE id = ?", (transfer_id,)).fetchone()
        if row is None:
            return None
        line_rows = self._db.execute(
            "SELECT * FROM stock_transfer_lines WHERE transfer_id = ?", (transfer_id,)
        ).fetchall()
        lines = [
            StockTransferLine(
                id=r["id"], product_id=r["product_id"], unit_id=r["unit_id"],
                requested_quantity=r["requested_quantity"], requested_weight=r["requested_weight"],
                approved_quantity=r["approved_quantity"], approved_weight=r["approved_weight"],
                reserved_quantity=r["reserved_quantity"], reserved_weight=r["reserved_weight"],
                picked_quantity=r["picked_quantity"], picked_weight=r["picked_weight"],
                dispatched_quantity=r["dispatched_quantity"], dispatched_weight=r["dispatched_weight"],
                received_quantity=r["received_quantity"], received_weight=r["received_weight"],
                accepted_quantity=r["accepted_quantity"], accepted_weight=r["accepted_weight"],
                rejected_quantity=r["rejected_quantity"], rejected_weight=r["rejected_weight"],
                pieces=r["pieces"], lot_required=bool(r["lot_required"]),
                quality_required=bool(r["quality_required"]),
                temperature_required=bool(r["temperature_required"]),
                temperature_at_pick=r["temperature_at_pick"], notes=r["notes"])
            for r in line_rows
        ]
        origin = TransferNode(
            node_type=TransferNodeType(row["origin_node_type"]),
            branch_id=row["origin_branch_id"], warehouse_id=row["origin_warehouse_id"],
            location_id=row["origin_location_id"])
        destination = TransferNode(
            node_type=TransferNodeType(row["destination_node_type"]),
            branch_id=row["destination_branch_id"], warehouse_id=row["destination_warehouse_id"],
            location_id=row["destination_location_id"])
        return StockTransfer(
            id=row["id"], transfer_number=row["transfer_number"],
            transfer_type=TransferType(row["transfer_type"]), origin_node=origin,
            destination_node=destination, requested_by_user_id=row["requested_by_user_id"],
            operation_id=row["operation_id"], lines=lines,
            status=TransferStatus(row["status"]), approved_by_user_id=row["approved_by_user_id"],
            priority=row["priority"], source_channel=row["source_channel"],
            source_reference_id=row["source_document_id"],
            blind_receipt_required=bool(row["blind_receipt_required"]),
            transport_required=bool(row["transport_required"]),
            cold_chain_required=bool(row["cold_chain_required"]),
            created_at=row["created_at"], updated_at=row["updated_at"])

    def operation_exists(self, operation_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM transfer_operations WHERE operation_id = ? LIMIT 1",
            (operation_id,)).fetchone()
        return row is not None

    # ── writes ───────────────────────────────────────────────────────────────
    def save(self, transfer: StockTransfer) -> None:
        exists = self._db.execute(
            "SELECT 1 FROM stock_transfers WHERE id = ? LIMIT 1", (transfer.id,)).fetchone()
        if exists is None:
            self._insert(transfer)
        else:
            self._update(transfer)
        self._save_lines(transfer)

    def _insert(self, transfer: StockTransfer) -> None:
        self._db.execute(
            """INSERT INTO stock_transfers (
                id, transfer_number, transfer_type, source_channel, source_module,
                source_document_id, origin_node_type, origin_branch_id, origin_warehouse_id,
                origin_location_id, destination_node_type, destination_branch_id,
                destination_warehouse_id, destination_location_id, requested_by_user_id,
                approved_by_user_id, priority, status, reason_code, business_reason,
                transport_required, cold_chain_required, blind_receipt_required,
                operation_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                transfer.id, transfer.transfer_number, transfer.transfer_type.value,
                transfer.source_channel, "transfers", transfer.source_reference_id,
                transfer.origin_node.node_type.value, transfer.origin_node.branch_id,
                transfer.origin_node.warehouse_id, transfer.origin_node.location_id,
                transfer.destination_node.node_type.value, transfer.destination_node.branch_id,
                transfer.destination_node.warehouse_id, transfer.destination_node.location_id,
                transfer.requested_by_user_id, transfer.approved_by_user_id, transfer.priority,
                transfer.status.value, None, None,
                int(transfer.transport_required), int(transfer.cold_chain_required),
                int(transfer.blind_receipt_required), transfer.operation_id,
                transfer.created_at, transfer.updated_at,
            ))

    def _update(self, transfer: StockTransfer) -> None:
        self._db.execute(
            """UPDATE stock_transfers SET
                status = ?, priority = ?, approved_by_user_id = ?, updated_at = ?
            WHERE id = ?""",
            (transfer.status.value, transfer.priority, transfer.approved_by_user_id,
             transfer.updated_at, transfer.id))

    def _save_lines(self, transfer: StockTransfer) -> None:
        for line in transfer.lines:
            exists = self._db.execute(
                "SELECT 1 FROM stock_transfer_lines WHERE id = ? LIMIT 1", (line.id,)).fetchone()
            values = tuple(str(getattr(line, col)) for col in _LINE_NUMERIC_COLUMNS)
            if exists is None:
                self._db.execute(
                    """INSERT INTO stock_transfer_lines (
                        id, transfer_id, product_id, unit_id, requested_quantity, requested_weight,
                        approved_quantity, approved_weight, reserved_quantity, reserved_weight,
                        picked_quantity, picked_weight, dispatched_quantity, dispatched_weight,
                        received_quantity, received_weight, accepted_quantity, accepted_weight,
                        rejected_quantity, rejected_weight, pieces, lot_required, quality_required,
                        temperature_required, temperature_at_pick, notes
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (line.id, transfer.id, line.product_id, line.unit_id, *values,
                     int(line.lot_required), int(line.quality_required),
                     int(line.temperature_required),
                     str(line.temperature_at_pick) if line.temperature_at_pick is not None else None,
                     line.notes))
            else:
                self._db.execute(
                    f"""UPDATE stock_transfer_lines SET {
                        ', '.join(f'{col} = ?' for col in _LINE_NUMERIC_COLUMNS)}
                    WHERE id = ?""",
                    (*values, line.id))

    def record_operation(self, *, transfer_id: str, operation_id: str, operation_type: str) -> None:
        actor_row = self._db.execute(
            "SELECT requested_by_user_id FROM stock_transfers WHERE id = ?",
            (transfer_id,)).fetchone()
        actor_user_id = actor_row["requested_by_user_id"] if actor_row is not None else None
        self._db.execute(
            """INSERT INTO transfer_operations (
                id, operation_id, transfer_id, operation_type, actor_user_id, device_id,
                local_sequence, sync_status, occurred_at
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), operation_id, transfer_id, operation_type, actor_user_id, None, None,
             "CONFIRMED", _now()))
        self._db.commit()
