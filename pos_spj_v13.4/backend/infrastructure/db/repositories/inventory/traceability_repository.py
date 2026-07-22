"""TraceabilityRepository — genealogy edges + ledger-derived lot movement reads.

Two responsibilities, both read-heavy (§32):
- Persist explicit parent→child lot links (production/slaughter/repack).
- Read the ledger (``inventory_ledger`` + ``inventory_ledger_lines``) by lot, so
  the query service can derive where a lot came from (INCREASE movements) and
  where it went (DECREASE movements) without duplicating the ledger.
"""

from __future__ import annotations

from backend.domain.inventory.entities.traceability_link import TraceabilityLink
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
)


class TraceabilityRepository(InventoryRepositoryBase):
    # ── explicit genealogy edges ────────────────────────────────────────────
    def save(self, link: TraceabilityLink) -> None:
        self._execute(
            "INSERT INTO inventory_traceability_link (id, parent_lot_id, child_lot_id,"
            " link_type, product_id, quantity, weight, source_module,"
            " source_document_type, source_document_id, operation_id,"
            " created_by_user_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (link.id, link.parent_lot_id, link.child_lot_id,
             enum_value(link.link_type), link.product_id, dec_str(link.quantity),
             dec_str(link.weight), link.source_module, link.source_document_type,
             link.source_document_id, link.operation_id, link.created_by_user_id,
             link.created_at))

    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM inventory_traceability_link WHERE operation_id=?",
            (operation_id,))

    def parents_of(self, child_lot_id: str) -> list[dict]:
        """Explicit parent lots that fed into ``child_lot_id`` (upstream edge)."""
        return self._query(
            "SELECT * FROM inventory_traceability_link WHERE child_lot_id=?"
            " ORDER BY created_at", (child_lot_id,))

    def children_of(self, parent_lot_id: str) -> list[dict]:
        """Explicit child lots derived from ``parent_lot_id`` (downstream edge)."""
        return self._query(
            "SELECT * FROM inventory_traceability_link WHERE parent_lot_id=?"
            " ORDER BY created_at", (parent_lot_id,))

    # ── ledger-derived movement reads for a lot ─────────────────────────────
    def ledger_movements_for_lot(self, lot_id: str) -> list[dict]:
        """Every ledger movement that touched ``lot_id``, header + line joined,
        oldest first — the raw material for upstream/downstream derivation."""
        return self._query(
            "SELECT m.id AS movement_id, m.movement_type, m.branch_id, m.warehouse_id,"
            " m.source_module, m.source_document_type, m.source_document_id,"
            " m.operation_id, m.status, m.occurred_at, m.created_by_user_id,"
            " l.id AS line_id, l.product_id, l.quantity, l.weight, l.unit,"
            " l.from_location_id, l.to_location_id, l.from_status, l.to_status"
            " FROM inventory_ledger_lines l"
            " JOIN inventory_ledger m ON m.id = l.movement_id"
            " WHERE l.lot_id=? ORDER BY m.occurred_at, l.id", (lot_id,))
