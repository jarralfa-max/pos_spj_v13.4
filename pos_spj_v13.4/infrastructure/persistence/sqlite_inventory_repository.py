# infrastructure/persistence/sqlite_inventory_repository.py — SPJ ERP v13.4
"""
SQLite implementation of inventory persistence.

Wraps the inventario_actual and movimientos_inventario tables.
No business logic — pure data access.

Migration target for repositories/inventory_repository.py (legacy shim remains).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from infrastructure.persistence.base import BaseRepository

logger = logging.getLogger("spj.infrastructure.inventory_repository")


class SQLiteInventoryRepository(BaseRepository):
    """
    SQLite data-access for inventario_actual + movimientos_inventario.
    """

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_stock(self, product_id: int, branch_id: int) -> float:
        row = self._fetchone(
            "SELECT cantidad FROM inventario_actual WHERE producto_id=? AND sucursal_id=?",
            (product_id, branch_id),
        )
        if row:
            return float(row["cantidad"])
        # Fall back to productos.existencia for branches that haven't migrated
        row2 = self._fetchone(
            "SELECT existencia FROM productos WHERE id=?", (product_id,)
        )
        return float(row2["existencia"]) if row2 else 0.0

    def get_all_stock(self, branch_id: int) -> List[Dict]:
        rows = self._fetchall("""
            SELECT ia.producto_id, p.nombre, p.unidad,
                   ia.cantidad, ia.costo_promedio,
                   p.stock_minimo
            FROM inventario_actual ia
            JOIN productos p ON p.id = ia.producto_id
            WHERE ia.sucursal_id = ?
            ORDER BY p.nombre
        """, (branch_id,))
        return [dict(r) for r in rows]

    def get_low_stock(self, branch_id: int) -> List[Dict]:
        rows = self._fetchall("""
            SELECT ia.producto_id, p.nombre,
                   ia.cantidad, p.stock_minimo, p.unidad
            FROM inventario_actual ia
            JOIN productos p ON p.id = ia.producto_id
            WHERE ia.sucursal_id = ?
              AND ia.cantidad <= p.stock_minimo
            ORDER BY (ia.cantidad - p.stock_minimo) ASC
        """, (branch_id,))
        return [dict(r) for r in rows]

    def get_movements(
        self,
        product_id: int,
        branch_id: int,
        limit: int = 50,
    ) -> List[Dict]:
        rows = self._fetchall("""
            SELECT movement_type, quantity, usuario, created_at,
                   operation_id, reference_type
            FROM movimientos_inventario
            WHERE product_id = ? AND branch_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (product_id, branch_id, limit))
        return [dict(r) for r in rows]

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_stock(
        self,
        product_id: int,
        branch_id: int,
        quantity: float,
        average_cost: float = 0.0,
    ) -> None:
        """Set absolute stock level (used for adjustments and initial load)."""
        self._execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, costo_promedio,
                                          ultima_actualizacion)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad = excluded.cantidad,
                costo_promedio = excluded.costo_promedio,
                ultima_actualizacion = excluded.ultima_actualizacion
        """, (product_id, branch_id, quantity, average_cost))

    def add_stock(
        self,
        product_id: int,
        branch_id: int,
        quantity: float,
        average_cost: float = 0.0,
    ) -> None:
        """Increment stock (entry / purchase)."""
        self._execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, costo_promedio,
                                          ultima_actualizacion)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad = cantidad + excluded.cantidad,
                costo_promedio = CASE WHEN excluded.costo_promedio > 0
                    THEN (cantidad * costo_promedio + excluded.cantidad * excluded.costo_promedio)
                         / (cantidad + excluded.cantidad)
                    ELSE costo_promedio END,
                ultima_actualizacion = excluded.ultima_actualizacion
        """, (product_id, branch_id, quantity, average_cost))

    def deduct_stock(self, product_id: int, branch_id: int, quantity: float) -> None:
        """Decrement stock (sale / consumption)."""
        self._execute("""
            UPDATE inventario_actual
            SET cantidad = cantidad - ?,
                ultima_actualizacion = datetime('now')
            WHERE producto_id = ? AND sucursal_id = ?
        """, (quantity, product_id, branch_id))

    def log_movement(
        self,
        product_id: int,
        branch_id: int,
        quantity: float,
        movement_type: str,
        operation_id: str,
        user: str,
        reference_type: str = "",
        reference_id: str = "",
        notes: str = "",
    ) -> None:
        """Append an immutable movement record."""
        self._execute("""
            INSERT INTO movimientos_inventario (
                product_id, branch_id, quantity, movement_type,
                operation_id, usuario, reference_type, reference_id,
                notes, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
        """, (
            product_id, branch_id, quantity, movement_type,
            operation_id, user, reference_type, reference_id, notes,
        ))
