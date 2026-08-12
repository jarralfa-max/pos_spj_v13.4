"""MovementQueryService — the read the Movimientos UI consults (§15).

Read-only projection over ``inventory_ledger``: lists recent posted movements
(most recent first, bounded) for display — date, type, source module/document and
status. It never writes; movements are appended only by the posting use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)
from backend.infrastructure.db.repositories.inventory.inventory_ledger_repository import (
    InventoryLedgerRepository,
)


class MovementQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    limit: int = 100) -> list[dict]:
        """Recent ledger movements (most recent first), optionally scoped to a
        branch and bounded by ``limit`` so the UI never pulls the whole ledger."""
        cols = ("id, movement_type, branch_id, warehouse_id, source_module,"
                " source_document_type, source_document_id, status, occurred_at")
        lim = max(1, int(limit))
        if branch_id:
            rows = self._query(
                f"SELECT {cols} FROM inventory_ledger WHERE branch_id=?"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (branch_id, lim))
        else:
            rows = self._query(
                f"SELECT {cols} FROM inventory_ledger"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (lim,))
        return [dict(r) | {"source_document_id": zn(r["source_document_id"])}
                for r in rows]

    def get_movement(self, *, movement_id: str) -> dict | None:
        """Full raw ledger header (§6 detalle) — for the movement detail view,
        not the display-ready list rows."""
        return InventoryLedgerRepository(self._conn).get(movement_id)

    def get_lines(self, *, movement_id: str) -> list[dict]:
        """This movement's ledger lines (§6 detalle/líneas)."""
        return InventoryLedgerRepository(self._conn).get_lines(movement_id)

    def list_for_document(self, *, source_document_type: str,
                          source_document_id: str) -> list[dict]:
        """Every ledger movement tied to the same source document (§6 documento
        origen) — e.g. all inventory effects of one purchase receipt or sale."""
        return InventoryLedgerRepository(self._conn).list_for_document(
            source_document_type, source_document_id)

    def list_for_lot(self, *, lot_id: str, limit: int = 100) -> list[dict]:
        """Every ledger movement with at least one line touching this lot
        (§26 "Ver movimientos"), most recent first."""
        lid = str(lot_id or "").strip()
        if not lid:
            return []
        cols = ("m.id, m.movement_type, m.branch_id, m.warehouse_id, m.source_module,"
                " m.source_document_type, m.source_document_id, m.status, m.occurred_at")
        rows = self._query(
            f"SELECT DISTINCT {cols} FROM inventory_ledger m"
            " JOIN inventory_ledger_lines l ON l.movement_id = m.id"
            " WHERE l.lot_id=? ORDER BY m.occurred_at DESC, m.id DESC LIMIT ?",
            (lid, max(1, int(limit))))
        return [dict(r) | {"source_document_id": zn(r["source_document_id"])}
                for r in rows]
