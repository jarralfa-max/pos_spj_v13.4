"""Canonical repository for inventory_stock and inventory_movements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.shared.ids import new_uuid


@dataclass(frozen=True)
class InventoryStockRecord:
    product_id: str
    branch_id: str
    quantity: float
    unit: str
    updated_at: str | None = None


@dataclass(frozen=True)
class InventoryMovementRecord:
    operation_id: str
    product_id: str
    branch_id: str
    movement_type: str
    quantity: float
    stock_before: float
    stock_after: float
    unit: str
    source_module: str
    reference_type: str | None = None
    reference_id: str | None = None
    reason: str | None = None
    user_name: str | None = None
    created_at: str | None = None


class InventoryRepository:
    """Persistence adapter for canonical inventory tables only."""

    def __init__(self, connection) -> None:
        self._connection = connection

    @property
    def connection(self):
        return self._connection

    def get_stock(self, product_id: str, branch_id: str) -> InventoryStockRecord:
        row = self._connection.execute(
            """
            SELECT product_id, branch_id, quantity, unit, updated_at
            FROM inventory_stock
            WHERE product_id = ? AND branch_id = ?
            """,
            (str(product_id), str(branch_id)),
        ).fetchone()
        if row is None:
            return InventoryStockRecord(
                product_id=str(product_id),
                branch_id=str(branch_id),
                quantity=0.0,
                unit="unit",
                updated_at=None,
            )
        return InventoryStockRecord(
            product_id=str(row[0]),
            branch_id=str(row[1]),
            quantity=float(row[2] or 0.0),
            unit=str(row[3] or "unit"),
            updated_at=None if row[4] is None else str(row[4]),
        )

    def list_stock(self, branch_id: str) -> list[InventoryStockRecord]:
        rows = self._connection.execute(
            """
            SELECT product_id, branch_id, quantity, unit, updated_at
            FROM inventory_stock
            WHERE branch_id = ?
            ORDER BY product_id
            """,
            (str(branch_id),),
        ).fetchall()
        return [
            InventoryStockRecord(
                product_id=str(row[0]),
                branch_id=str(row[1]),
                quantity=float(row[2] or 0.0),
                unit=str(row[3] or "unit"),
                updated_at=None if row[4] is None else str(row[4]),
            )
            for row in rows
        ]

    def list_movements(
        self,
        *,
        product_id: str | None = None,
        branch_id: str | None = None,
    ) -> list[InventoryMovementRecord]:
        filters: list[str] = []
        params: list[Any] = []
        if product_id is not None:
            filters.append("product_id = ?")
            params.append(str(product_id))
        if branch_id is not None:
            filters.append("branch_id = ?")
            params.append(str(branch_id))
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = self._connection.execute(
            f"""
            SELECT operation_id, product_id, branch_id, movement_type, quantity,
                   stock_before, stock_after, unit, source_module, reference_type,
                   reference_id, reason, user_name, created_at
            FROM inventory_movements
            {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
        return [self._movement_from_row(row) for row in rows]

    def get_movement(
        self,
        *,
        operation_id: str,
        product_id: str,
        branch_id: str,
        movement_type: str,
    ) -> InventoryMovementRecord | None:
        row = self._connection.execute(
            """
            SELECT operation_id, product_id, branch_id, movement_type, quantity,
                   stock_before, stock_after, unit, source_module, reference_type,
                   reference_id, reason, user_name, created_at
            FROM inventory_movements
            WHERE operation_id = ? AND product_id = ? AND branch_id = ? AND movement_type = ?
            LIMIT 1
            """,
            (str(operation_id), str(product_id), str(branch_id), movement_type),
        ).fetchone()
        return None if row is None else self._movement_from_row(row)

    def record_movement(self, movement: InventoryMovementRecord) -> InventoryMovementRecord:
        existing = self.get_movement(
            operation_id=movement.operation_id,
            product_id=movement.product_id,
            branch_id=movement.branch_id,
            movement_type=movement.movement_type,
        )
        if existing is not None:
            return existing
        self._connection.execute(
            """
            INSERT INTO inventory_stock (product_id, branch_id, quantity, unit, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(product_id, branch_id) DO UPDATE SET
                quantity = excluded.quantity,
                unit = excluded.unit,
                updated_at = CURRENT_TIMESTAMP
            """,
            (movement.product_id, movement.branch_id, movement.stock_after, movement.unit),
        )
        self._connection.execute(
            """
            INSERT INTO inventory_movements
            (id, operation_id, product_id, branch_id, movement_type, quantity,
             stock_before, stock_after, unit, source_module, reference_type,
             reference_id, reason, user_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_uuid(),
                movement.operation_id,
                movement.product_id,
                movement.branch_id,
                movement.movement_type,
                movement.quantity,
                movement.stock_before,
                movement.stock_after,
                movement.unit,
                movement.source_module,
                movement.reference_type,
                movement.reference_id,
                movement.reason,
                movement.user_name,
            ),
        )
        return movement

    def commit(self) -> None:
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def rollback(self) -> None:
        if hasattr(self._connection, "rollback"):
            self._connection.rollback()

    @staticmethod
    def _movement_from_row(row) -> InventoryMovementRecord:
        return InventoryMovementRecord(
            operation_id=str(row[0]),
            product_id=str(row[1]),
            branch_id=str(row[2]),
            movement_type=str(row[3]),
            quantity=float(row[4] or 0.0),
            stock_before=float(row[5] or 0.0),
            stock_after=float(row[6] or 0.0),
            unit=str(row[7] or "unit"),
            source_module=str(row[8]),
            reference_type=None if row[9] is None else str(row[9]),
            reference_id=None if row[10] is None else str(row[10]),
            reason=None if row[11] is None else str(row[11]),
            user_name=None if row[12] is None else str(row[12]),
            created_at=None if row[13] is None else str(row[13]),
        )
