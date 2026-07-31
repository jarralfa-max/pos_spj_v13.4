"""Read-only Logistics queries consumed by desktop Procurement references."""

from __future__ import annotations

import sqlite3


class LogisticsShipmentQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def related_to_destination(self, *, branch_id: str, warehouse_id: str,
                               limit: int = 100) -> list[dict]:
        try:
            cursor = self._connection.execute(
                "SELECT id,shipment_number,origin_type,status,started_at,dispatched_at"
                " FROM logistics_shipments WHERE destination_branch_id=?"
                " AND destination_warehouse_id=? ORDER BY started_at DESC LIMIT ?",
                (branch_id, warehouse_id, limit))
        except sqlite3.OperationalError:
            return []
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
