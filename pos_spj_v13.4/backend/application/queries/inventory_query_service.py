"""QueryService for canonical inventory UI/API read models."""

from __future__ import annotations

import logging

from backend.infrastructure.db.repositories.inventory_repository import (
    InventoryMovementRecord,
    InventoryRepository,
    InventoryStockRecord,
)


logger = logging.getLogger("spj.inventory.query")


def _tbl_exists(conn, name: str) -> bool:
    try:
        r = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return r is not None
    except Exception:
        return False


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
        """
        Return product stock rows for UI tables.

        Reads from inventario_actual (written by UnifiedInventoryService/production)
        and inventory_stock (written by InventoryApplicationService/purchases). Both
        tables store branch-specific stock — neither leaks global values. productos.existencia
        is intentionally excluded (it is a global sum and must NOT be used as stock source).
        """
        has_inv_actual = _tbl_exists(self._connection, "inventario_actual")
        has_inv_stock = _tbl_exists(self._connection, "inventory_stock")

        if has_inv_actual and has_inv_stock:
            try:
                return self._connection.execute(
                    """
                    SELECT p.id,
                           p.nombre,
                           COALESCE(p.categoria, ''),
                           COALESCE(ia.cantidad, s.quantity, 0) AS qty,
                           COALESCE(p.stock_minimo, 0),
                           COALESCE(p.unidad, 'kg')
                    FROM productos p
                    LEFT JOIN inventario_actual ia
                        ON ia.producto_id = p.id AND ia.sucursal_id = ?
                    LEFT JOIN inventory_stock s
                        ON s.product_id = p.id AND s.branch_id = ?
                    WHERE COALESCE(p.activo, 1) = 1
                    ORDER BY p.nombre
                    """,
                    (int(branch_id), int(branch_id)),
                ).fetchall()
            except Exception:
                logger.exception("Error listing inventory stock rows for branch_id=%s", branch_id)
                return []

        if has_inv_actual:
            try:
                return self._connection.execute(
                    """
                    SELECT p.id, p.nombre, COALESCE(p.categoria, ''),
                           COALESCE(ia.cantidad, 0), COALESCE(p.stock_minimo, 0),
                           COALESCE(p.unidad, 'kg')
                    FROM productos p
                    LEFT JOIN inventario_actual ia
                        ON ia.producto_id = p.id AND ia.sucursal_id = ?
                    WHERE COALESCE(p.activo, 1) = 1
                    ORDER BY p.nombre
                    """,
                    (int(branch_id),),
                ).fetchall()
            except Exception:
                logger.exception("Error listing inventory stock rows (ia-only) for branch_id=%s", branch_id)
                return []

        try:
            return self._connection.execute(
                """
                SELECT p.id, p.nombre, COALESCE(p.categoria, ''),
                       COALESCE(s.quantity, 0), COALESCE(p.stock_minimo, 0),
                       COALESCE(s.unit, p.unidad, 'kg')
                FROM productos p
                LEFT JOIN inventory_stock s
                    ON s.product_id = p.id AND s.branch_id = ?
                WHERE COALESCE(p.activo, 1) = 1
                ORDER BY p.nombre
                """,
                (int(branch_id),),
            ).fetchall()
        except Exception:
            logger.exception("Error listing inventory stock rows (is-only) for branch_id=%s", branch_id)
            return []

    def list_availability_rows(self, branch_id: int) -> list[dict]:
        """Return physical and sale availability from inventario_actual (canonical)."""
        has_reservas = _tbl_exists(self._connection, "stock_reserva_detalles")
        res_join = (
            """LEFT JOIN (
                    SELECT d.producto_id, SUM(d.cantidad) AS reserved_qty
                    FROM stock_reserva_detalles d
                    JOIN stock_reservas r ON r.id = d.reserva_id
                    WHERE r.estado = 'activa' AND r.branch_id = ?
                    GROUP BY d.producto_id
                ) res ON res.producto_id = p.id"""
            if has_reservas
            else ""
        )
        params = [int(branch_id)]
        if has_reservas:
            params = [int(branch_id), int(branch_id)]
        try:
            rows = self._connection.execute(
                f"""
                SELECT p.id,
                       p.nombre,
                       COALESCE(ia.cantidad, 0) AS physical_stock,
                       {'COALESCE(res.reserved_qty, 0)' if has_reservas else '0'} AS reserved_qty
                FROM productos p
                LEFT JOIN inventario_actual ia
                    ON ia.producto_id = p.id AND ia.sucursal_id = ?
                {res_join}
                WHERE COALESCE(p.activo, 1) = 1
                ORDER BY p.nombre
                """,
                params,
            ).fetchall()
        except Exception:
            logger.exception("Error listing inventory availability rows for branch_id=%s", branch_id)
            return []

        out: list[dict] = []
        for row in rows:
            product_id = int(row[0])
            physical = float(row[2] or 0.0)
            reserved = float(row[3] or 0.0)
            available = max(0.0, physical - reserved)
            out.append({
                "product_id": product_id,
                "name": str(row[1] or ""),
                "physical_stock": physical,
                "reserved": reserved,
                "physical_available": available,
                "virtual_available": None,
                "sale_available": available,
                "mode": "DIRECTO" if available > 0 else "NO DISPONIBLE",
            })
        return out

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
            logger.exception("Error loading last movement map for branch_id=%s", branch_id)
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
            logger.exception("Error counting today inventory movements for branch_id=%s", branch_id)
            movements_today = 0
        reserved_total = 0.0
        try:
            availability = self.list_availability_rows(branch_id)
            reserved_total = sum(float(row.get("reserved") or 0.0) for row in availability)
        except Exception:
            logger.exception("Error calculating reserved KPI for branch_id=%s", branch_id)
        return {
            "stock_bajo": stock_low,
            "sin_stock_fisico": out_of_stock,
            "virtual_disponible": None,
            "reservados": reserved_total,
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
            logger.exception("Error listing recent inventory movements for branch_id=%s", branch_id)
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
            logger.exception("Error listing product inventory history product_id=%s branch_id=%s", product_id, branch_id)
            return []

    # Backward-compatible aliases for tests/use cases that already depend on the
    # canonical QueryService object, not on the legacy core service module.
    def list_inventory_rows(self, branch_id: int):
        return self.list_stock_rows(branch_id)

    def get_last_movement_by_product(self, branch_id: int) -> dict[int, str]:
        return self.get_last_movement_map(branch_id)
