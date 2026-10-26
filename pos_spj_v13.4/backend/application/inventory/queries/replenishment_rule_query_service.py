"""Lectura de reglas de reposición y almacenes para el alta de productos."""

from __future__ import annotations

import sqlite3


class ReplenishmentRuleQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def warehouses(self, branch_id: str) -> list[tuple[str, str]]:
        if not branch_id:
            return []
        try:
            rows = self._connection.execute(
                "SELECT id, code || ' · ' || name FROM warehouses "
                "WHERE branch_id=? AND status='ACTIVE' ORDER BY name", (branch_id,)
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(str(row[0]), str(row[1])) for row in rows]

    def rule(self, product_id: str, branch_id: str, warehouse_id: str) -> dict | None:
        if warehouse_id not in {key for key, _ in self.warehouses(branch_id)}:
            return None
        try:
            row = self._connection.execute(
                "SELECT reorder_point, target_quantity, active "
                "FROM inventory_replenishment_rule "
                "WHERE product_id=? AND branch_id=? AND warehouse_id=?",
                (product_id, branch_id, warehouse_id),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return ({"minimum": str(row[0]), "target": str(row[1]),
                 "active": bool(row[2])} if row is not None else None)
