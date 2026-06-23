# infrastructure/persistence/sqlite_inventory_repository.py — SPJ ERP v13.4
"""SQLite implementation of inventory persistence (UUID-only)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from infrastructure.persistence.base import BaseRepository

logger = logging.getLogger("spj.infrastructure.inventory_repository")


class SQLiteInventoryRepository(BaseRepository):
    """SQLite data-access for inventory_stock + movimientos_inventario.

    Identity contract: product_id and branch_id are UUIDv7 TEXT strings.
    Reads from inventory_stock (canonical, branch-aware).
    """

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_stock(self, product_id: str, branch_id: str) -> float:
        row = self._fetchone(
            "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
            (product_id, branch_id),
        )
        if row:
            return float(row["quantity"])
        row2 = self._fetchone(
            "SELECT COALESCE(existencia, 0) AS existencia FROM productos WHERE id=?",
            (product_id,),
        )
        return float(row2["existencia"]) if row2 else 0.0

    def get_all_stock(self, branch_id: str) -> List[Dict]:
        rows = self._fetchall("""
            SELECT s.product_id, p.nombre, p.unidad,
                   s.quantity AS cantidad, COALESCE(p.stock_minimo, 0) AS stock_minimo
            FROM inventory_stock s
            JOIN productos p ON p.id = s.product_id
            WHERE s.branch_id = ?
            ORDER BY p.nombre
        """, (branch_id,))
        return [dict(r) for r in rows]

    def get_low_stock(self, branch_id: str) -> List[Dict]:
        rows = self._fetchall("""
            SELECT s.product_id, p.nombre,
                   s.quantity AS cantidad, COALESCE(p.stock_minimo, 0) AS stock_minimo,
                   p.unidad
            FROM inventory_stock s
            JOIN productos p ON p.id = s.product_id
            WHERE s.branch_id = ?
              AND s.quantity <= COALESCE(p.stock_minimo, 0)
            ORDER BY (s.quantity - COALESCE(p.stock_minimo, 0)) ASC
        """, (branch_id,))
        return [dict(r) for r in rows]

    def get_movements(
        self,
        product_id: str,
        branch_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        rows = self._fetchall("""
            SELECT movement_type, quantity, user_name AS usuario, created_at,
                   operation_id, reference_type
            FROM inventory_movements
            WHERE product_id = ? AND branch_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (product_id, branch_id, limit))
        return [dict(r) for r in rows]

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_stock(
        self,
        product_id: str,
        branch_id: str,
        quantity: float,
        unit: str = "kg",
    ) -> None:
        """Set absolute stock level (adjustments and initial load)."""
        self._execute("""
            INSERT INTO inventory_stock (product_id, branch_id, quantity, unit, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(product_id, branch_id) DO UPDATE SET
                quantity = excluded.quantity,
                updated_at = excluded.updated_at
        """, (product_id, branch_id, quantity, unit))

    def add_stock(
        self,
        product_id: str,
        branch_id: str,
        quantity: float,
        unit: str = "kg",
    ) -> None:
        """Increment stock (entry / purchase)."""
        self._execute("""
            INSERT INTO inventory_stock (product_id, branch_id, quantity, unit, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(product_id, branch_id) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                updated_at = excluded.updated_at
        """, (product_id, branch_id, quantity, unit))

    def deduct_stock(self, product_id: str, branch_id: str, quantity: float) -> None:
        """Decrement stock (sale / consumption)."""
        self._execute("""
            UPDATE inventory_stock
            SET quantity = quantity - ?,
                updated_at = datetime('now')
            WHERE product_id = ? AND branch_id = ?
        """, (quantity, product_id, branch_id))

    def log_movement(
        self,
        product_id: str,
        branch_id: str,
        quantity: float,
        movement_type: str,
        operation_id: str,
        user: str,
        reference_type: str = "",
        reference_id: str = "",
        notes: str = "",
    ) -> None:
        """Append an immutable movement record."""
        from backend.shared.ids import new_uuid
        self._execute("""
            INSERT INTO inventory_movements (
                id, product_id, branch_id, quantity, movement_type,
                operation_id, user_name, reference_type, reference_id,
                notes, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
        """, (
            new_uuid(), product_id, branch_id, quantity, movement_type,
            operation_id, user, reference_type, reference_id, notes,
        ))
