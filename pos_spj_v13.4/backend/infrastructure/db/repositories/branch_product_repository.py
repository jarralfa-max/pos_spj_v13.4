"""SQLite-backed repository for branch-product configuration and price history.

Extracted from modulos/productos.py (F5): the PyQt UI used to run this SQL
inline. The UI now delegates reads/writes here and only builds widgets from the
returned data. PyQt-free and fully unit-testable.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class BranchProductRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    # ── reads ──────────────────────────────────────────────────────────────────
    def list_active_branches(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, nombre FROM sucursales WHERE activa=1 AND id IS NOT NULL AND TRIM(id) != '' AND LOWER(TRIM(id)) NOT IN ('none','null') ORDER BY nombre"
        ).fetchall()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    def list_branch_products(self, branch_id: str | None = None) -> list[dict[str, Any]]:
        base = """
            SELECT s.nombre AS suc_nombre, p.nombre AS prod_nombre,
                   bp.activo, bp.precio_local, bp.stock_min_local,
                   p.precio AS precio_global,
                   bp.branch_id, bp.product_id
            FROM branch_products bp
            JOIN sucursales s ON s.id = bp.branch_id
            JOIN productos   p ON p.id = bp.product_id
        """
        if branch_id:
            rows = self._connection.execute(
                base + " WHERE bp.branch_id = ? AND p.activo = 1 ORDER BY p.nombre",
                (branch_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                base + " WHERE p.activo = 1 ORDER BY s.nombre, p.nombre"
            ).fetchall()
        return [dict(r) for r in rows]

    def inactive_branches_for_product(self, product_id: str) -> str | None:
        row = self._connection.execute(
            """
            SELECT GROUP_CONCAT(s2.nombre, ', ')
            FROM sucursales s2
            LEFT JOIN branch_products bp2
                ON bp2.branch_id = s2.id AND bp2.product_id = ?
            WHERE s2.activa = 1
              AND (bp2.activo = 0 OR bp2.activo IS NULL)
            """,
            (product_id,),
        ).fetchone()
        return row[0] if row and row[0] else None

    def get_product_basic(self, product_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT nombre, precio, precio_compra FROM productos WHERE id=?",
            (product_id,),
        ).fetchone()
        if row is None:
            return None
        return {"nombre": row[0], "precio": row[1], "precio_compra": row[2]}

    def list_price_history(self, product_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT campo, precio_anterior, precio_nuevo,
                   diferencia_pct, usuario, changed_at
            FROM historial_precios
            WHERE producto_id=?
            ORDER BY changed_at DESC LIMIT ?
            """,
            (product_id, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── writes ─────────────────────────────────────────────────────────────────
    def upsert_branch_product(
        self, *, branch_id: str, product_id: str, activo: int,
        precio_local: float | None, stock_min_local: float | None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO branch_products(branch_id, product_id, activo, precio_local, stock_min_local)
            VALUES(?,?,?,?,?)
            ON CONFLICT(branch_id, product_id) DO UPDATE SET
                activo=excluded.activo,
                precio_local=excluded.precio_local,
                stock_min_local=excluded.stock_min_local,
                updated_at=datetime('now')
            """,
            (branch_id, product_id, activo, precio_local, stock_min_local),
        )
