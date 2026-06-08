"""QueryService for canonical inventory UI/API read models."""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory_repository import (
    InventoryMovementRecord,
    InventoryRepository,
    InventoryStockRecord,
)


class InventoryQueryService:
    """Read-only application service backed by canonical inventory tables."""

    def __init__(self, repository: InventoryRepository) -> None:
        self._repository = repository
        self._connection = repository.connection

    def get_stock(self, product_id: int, branch_id: int) -> InventoryStockRecord:
        return self._repository.get_stock(product_id=int(product_id), branch_id=int(branch_id))

    def list_stock(self, branch_id: int) -> list[InventoryStockRecord]:
        return self._repository.list_stock(branch_id=int(branch_id))

    def list_movements(
        self,
        product_id: int | None = None,
        branch_id: int | None = None,
    ) -> list[InventoryMovementRecord]:
        return self._repository.list_movements(product_id=product_id, branch_id=branch_id)

    def list_stock_rows(self, branch_id: int):
        """Return product stock rows for UI tables from inventory_stock only."""

        try:
            return self._connection.execute(
                """
                SELECT p.id,
                       p.nombre,
                       COALESCE(p.categoria, ''),
                       COALESCE(s.quantity, 0),
                       COALESCE(p.stock_minimo, 0),
                       COALESCE(s.unit, p.unidad, 'unit')
                FROM productos p
                LEFT JOIN inventory_stock s
                    ON s.product_id = p.id AND s.branch_id = ?
                WHERE COALESCE(p.activo, 1) = 1
                ORDER BY p.nombre
                """,
                (int(branch_id),),
            ).fetchall()
        except Exception:
            return []

    def get_last_movement_map(self, branch_id: int) -> dict[int, str]:
        try:
            rows = self._connection.execute(
                """
                SELECT product_id, MAX(created_at)
                FROM inventory_movements
                WHERE branch_id = ?
                GROUP BY product_id
                """,
                (int(branch_id),),
            ).fetchall()
            return {int(row[0]): str(row[1] or "")[:16] for row in rows}
        except Exception:
            return {}

    def get_operational_kpis(self, branch_id: int, product_data: list[dict] | None = None, **kwargs) -> dict:
        product_data = product_data if product_data is not None else kwargs.get("prod_data", [])
        stock_low = sum(1 for product in product_data if product.get("health") == "BAJO MÍN.")
        out_of_stock = sum(1 for product in product_data if product.get("health") == "SIN STOCK")
        movements_today = 0
        try:
            row = self._connection.execute(
                """
                SELECT COUNT(*)
                FROM inventory_movements
                WHERE branch_id = ? AND DATE(created_at) = DATE('now')
                """,
                (int(branch_id),),
            ).fetchone()
            movements_today = int((row[0] if row else 0) or 0)
        except Exception:
            movements_today = 0
        return {
            "stock_bajo": stock_low,
            "sin_stock_fisico": out_of_stock,
            "virtual_disponible": 0,
            "reservados": 0,
            "mov_hoy": movements_today,
        }

    def list_recent_movements(self, branch_id: int, limit: int = 200):
        try:
            return self._connection.execute(
                """
                SELECT im.created_at,
                       p.nombre,
                       im.movement_type,
                       im.quantity,
                       im.branch_id,
                       COALESCE(im.reference_type, ''),
                       COALESCE(im.user_name, ''),
                       COALESCE(im.source_module, '')
                FROM inventory_movements im
                JOIN productos p ON p.id = im.product_id
                WHERE im.branch_id = ?
                ORDER BY im.created_at DESC, im.id DESC
                LIMIT ?
                """,
                (int(branch_id), int(limit)),
            ).fetchall()
        except Exception:
            return []

    def list_feed_movements(self, branch_id: int, limit: int = 12) -> list[dict]:
        rows = self.list_recent_movements(branch_id=branch_id, limit=limit)
        return [
            {
                "created_at": row[0],
                "nombre": row[1],
                "movement_type": row[2],
                "quantity": row[3],
                "branch_id": row[4],
                "reference_type": row[5],
                "usuario": row[6],
                "source_module": row[7],
            }
            for row in rows
        ]

    def list_product_history(self, product_id: int, branch_id: int, limit: int = 100):
        try:
            return self._connection.execute(
                """
                SELECT created_at,
                       movement_type,
                       quantity,
                       COALESCE(user_name, ''),
                       COALESCE(reference_type, ''),
                       COALESCE(operation_id, '')
                FROM inventory_movements
                WHERE product_id = ? AND branch_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (int(product_id), int(branch_id), int(limit)),
            ).fetchall()
        except Exception:
            return []

    # Backward-compatible aliases for tests/use cases that already depend on the
    # canonical QueryService object, not on the legacy core service module.
    def list_inventory_rows(self, branch_id: int):
        return self.list_stock_rows(branch_id)

    def get_last_movement_by_product(self, branch_id: int) -> dict[int, str]:
        return self.get_last_movement_map(branch_id)
