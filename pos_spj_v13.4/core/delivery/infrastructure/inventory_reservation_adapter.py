from __future__ import annotations

import logging
from typing import Any

from core.services.reservation_service import ReservationService

logger = logging.getLogger("spj.delivery.inventory.adapter")


class ReservationServiceInventoryAdapter:
    """InventoryReservationPort implementation backed by ReservationService.

    It keeps delivery application code independent from the concrete inventory
    implementation while preserving the legacy reservation tables.
    """

    def __init__(self, db, reservation_service: ReservationService | None = None) -> None:
        if db is None:
            raise ValueError("ReservationServiceInventoryAdapter requiere una conexión SQLite válida.")
        self.db = db
        self.reservation_service = reservation_service or ReservationService()
        self._ensure_reservation_schema()


    def _ensure_reservation_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_reservations (
                id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                reserved_qty REAL NOT NULL CHECK(reserved_qty > 0),
                operation_id TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                expires_at DATETIME NOT NULL,
                released INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventory_reservations_operation "
            "ON inventory_reservations(operation_id, product_id, branch_id, released)"
        )
        self.db.commit()

    def reserve_for_order(
        self,
        *,
        order_id: str,
        items: list[dict[str, Any]],
        branch_id: str,
        operation_id: str,
    ) -> dict[str, int]:
        reserved = 0
        skipped = 0
        for item in items or []:
            product_id = item.get("product_id")
            qty = float(item.get("cantidad") or item.get("qty") or 0)
            if not product_id or qty <= 0:
                skipped += 1
                continue
            if self._active_reservation_exists(operation_id, str(product_id), str(branch_id)):
                skipped += 1
                continue
            self.reservation_service.reserve(
                db=self.db,
                product_id=str(product_id),
                qty=qty,
                operation_id=operation_id,
                branch_id=str(branch_id),
                operation_type="delivery",
            )
            reserved += 1
        return {"reserved": reserved, "skipped": skipped}

    def release_for_order(self, *, order_id: str, operation_id: str, reason: str = "") -> dict[str, int]:
        released = self.reservation_service.release_by_operation(self.db, operation_id=operation_id)
        return {"released": int(released or 0)}

    def commit_for_order(
        self,
        *,
        order_id: str,
        items: list[dict[str, Any]],
        branch_id: str,
        operation_id: str,
    ) -> dict[str, int]:
        committed = 0
        skipped = 0
        from core.services.inventory_service import InventoryService

        inventory_service = InventoryService(self.db)
        for item in items or []:
            product_id = item.get("product_id")
            qty = self._commit_qty(item)
            if not product_id or qty <= 0:
                skipped += 1
                continue
            item_operation_id = self._item_operation_id(order_id, item, str(product_id))
            if self._movement_exists(item_operation_id):
                skipped += 1
                continue
            inventory_service.deduct_stock(
                product_id=str(product_id),
                branch_id=str(branch_id),
                qty=qty,
                reference_type="delivery_prepared",
                reference_id=str(order_id),
                operation_id=item_operation_id,
                user="sistema",
                notes=f"delivery final/prepared qty={qty:.3f} source_op={operation_id}",
            )
            committed += 1
        released = self.reservation_service.release_by_operation(self.db, operation_id=operation_id)
        return {"committed": committed, "skipped": skipped, "released": int(released or 0)}

    def _active_reservation_exists(self, operation_id: str, product_id: str, branch_id: str) -> bool:
        row = self.db.execute(
            """
            SELECT 1 FROM inventory_reservations
            WHERE operation_id=? AND product_id=? AND branch_id=? AND released=0
            LIMIT 1
            """,
            (operation_id, product_id, branch_id),
        ).fetchone()
        return row is not None

    def _movement_exists(self, operation_id: str) -> bool:
        try:
            row = self.db.execute(
                "SELECT 1 FROM movimientos_inventario WHERE operation_id=? LIMIT 1",
                (operation_id,),
            ).fetchone()
            return row is not None
        except Exception as exc:
            logger.debug("movement idempotency check skipped op=%s: %s", operation_id, exc)
            return False

    @staticmethod
    def _commit_qty(item: dict[str, Any]) -> float:
        return float(item.get("final_qty") or item.get("prepared_qty") or item.get("cantidad") or item.get("qty") or 0)

    @staticmethod
    def _item_operation_id(order_id: str, item: dict[str, Any], product_id: str) -> str:
        item_id = item.get("id") or item.get("item_id") or product_id
        return f"delivery:{order_id}:item:{item_id}:commit"
