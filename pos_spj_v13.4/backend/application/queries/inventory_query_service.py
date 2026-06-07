"""Read-only QueryService for inventory desktop/API read models."""

from __future__ import annotations

from typing import Any, Iterable, Sequence


class InventoryQueryService:
    """Inventory reads owned by the application layer, not PyQt widgets."""

    def __init__(self, db) -> None:
        self._db = db

    def list_inventory_rows(self, *, branch_id: int) -> list[tuple[Any, ...]]:
        try:
            return list(self._db.execute(
                "SELECT p.id, p.nombre, COALESCE(p.categoria,''), "
                "COALESCE(bi.quantity, p.existencia, 0), "
                "COALESCE(p.stock_minimo, 5), COALESCE(p.unidad,'pza') "
                "FROM productos p "
                "LEFT JOIN branch_inventory bi "
                "    ON bi.product_id=p.id AND bi.branch_id=? "
                "WHERE p.activo=1 ORDER BY p.nombre",
                [branch_id],
            ).fetchall())
        except Exception:
            return []

    def get_last_movement_by_product(self, *, branch_id: int) -> dict[int, str]:
        try:
            rows = self._db.execute(
                "SELECT product_id, MAX(created_at) "
                "FROM inventory_movements WHERE branch_id=? "
                "GROUP BY product_id",
                [branch_id],
            ).fetchall()
            return {int(row[0]): str(row[1] or "")[:16] for row in rows}
        except Exception:
            return {}

    def list_low_stock_alerts(self, *, limit: int = 8) -> list[tuple[Any, ...]]:
        try:
            return list(self._db.execute(
                "SELECT nombre, existencia, COALESCE(stock_minimo,5), unidad "
                "FROM productos WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1 "
                "ORDER BY existencia ASC LIMIT ?",
                [int(limit)],
            ).fetchall())
        except Exception:
            return []

    def list_recent_feed(self, *, branch_id: int, limit: int = 12) -> list[dict[str, Any]]:
        movements: list[dict[str, Any]] = []
        try:
            rows = self._db.execute(
                "SELECT im.movement_type, im.quantity, im.usuario, im.created_at, p.nombre "
                "FROM inventory_movements im "
                "JOIN productos p ON p.id = im.product_id "
                "WHERE im.branch_id = ? "
                "ORDER BY im.created_at DESC LIMIT ?",
                [branch_id, int(limit)],
            ).fetchall()
            for row in rows:
                movements.append({
                    "movement_type": row[0],
                    "quantity": row[1],
                    "usuario": row[2],
                    "created_at": row[3],
                    "nombre": row[4],
                })
        except Exception:
            movements = self._list_legacy_adjustment_feed(branch_id=branch_id, limit=limit)
        return movements

    def _list_legacy_adjustment_feed(self, *, branch_id: int, limit: int) -> list[dict[str, Any]]:
        try:
            rows = self._db.execute(
                "SELECT tipo, cantidad, usuario, created_at, "
                "(SELECT nombre FROM productos WHERE id=a.producto_id) "
                "FROM ajustes_inventario a "
                "WHERE sucursal_id=? ORDER BY created_at DESC LIMIT ?",
                [branch_id, int(limit)],
            ).fetchall()
            return [
                {
                    "movement_type": row[0],
                    "quantity": row[1],
                    "usuario": row[2],
                    "created_at": row[3],
                    "nombre": row[4],
                }
                for row in rows
            ]
        except Exception:
            return []

    def list_product_history(self, *, product_id: int, branch_id: int, limit: int = 100) -> list[tuple[Any, ...]]:
        try:
            return list(self._db.execute(
                "SELECT created_at, movement_type, quantity, usuario, "
                "COALESCE(reference_type,''), COALESCE(operation_id,'') "
                "FROM inventory_movements "
                "WHERE product_id=? AND branch_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                [product_id, branch_id, int(limit)],
            ).fetchall())
        except Exception:
            return []

    def list_recent_movements(self, *, branch_id: int, limit: int = 200) -> list[tuple[Any, ...]]:
        try:
            return list(self._db.execute(
                "SELECT im.created_at, p.nombre, im.movement_type, im.quantity, im.branch_id, "
                "COALESCE(im.reference,''), COALESCE(im.usuario,''), COALESCE(im.origin,'') "
                "FROM inventory_movements im JOIN productos p ON p.id=im.product_id "
                "WHERE im.branch_id=? ORDER BY im.created_at DESC LIMIT ?",
                [branch_id, int(limit)],
            ).fetchall())
        except Exception:
            return []

    def get_operational_kpis(self, *, branch_id: int, product_data: Sequence[dict[str, Any]]) -> dict[str, int]:
        stock_low = sum(1 for product in product_data if product.get("health") == "BAJO MÍN.")
        no_stock = sum(1 for product in product_data if product.get("health") == "SIN STOCK")
        movements_today = 0
        try:
            row = self._db.execute(
                "SELECT COUNT(*) FROM inventory_movements WHERE branch_id=? AND DATE(created_at)=DATE('now')",
                [branch_id],
            ).fetchone()
            movements_today = int((row[0] if row else 0) or 0)
        except Exception:
            movements_today = 0
        return {
            "stock_bajo": stock_low,
            "sin_stock_fisico": no_stock,
            "virtual_disponible": 0,
            "reservados": 0,
            "mov_hoy": movements_today,
        }
