"""Canonical warehouse lookup used to establish an explicit session context."""

from __future__ import annotations

import sqlite3


class WarehouseDirectoryQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def active_for_branch(self, branch_id: str) -> list[tuple[str, str]]:
        try:
            rows = self._connection.execute(
                "SELECT id, code || ' · ' || name FROM warehouses"
                " WHERE branch_id=? AND status='ACTIVE' AND allow_purchase_receipt=1"
                " ORDER BY name", (branch_id,)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(str(row[0]), str(row[1])) for row in rows]
