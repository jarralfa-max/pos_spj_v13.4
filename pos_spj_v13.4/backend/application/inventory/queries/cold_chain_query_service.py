"""ColdChainQueryService — the read the Cadena de frío UI consults (§21).

Read-only projection over ``inventory_temperature_excursions``: lists open
(unresolved) excursions, most recent first — warehouse, lot, temperature, range,
status and the action taken. It never writes; excursions are recorded and resolved
only by their use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
    zn,
)


class ColdChainQueryService(InventoryRepositoryBase):
    def list_open_excursions(self, *, warehouse_id: str | None = None) -> list[dict]:
        """Open temperature excursions (unresolved), most recent first. Rows carry
        warehouse, lot, temperature, range, status and action for display."""
        cols = ("id, warehouse_id, lot_id, status, temperature, min_temp, max_temp,"
                " action_taken, created_at")
        sql = (f"SELECT {cols} FROM inventory_temperature_excursions WHERE resolved=0")
        params: tuple = ()
        if warehouse_id:
            sql += " AND warehouse_id=?"
            params += (warehouse_id,)
        sql += " ORDER BY created_at DESC"
        return [{
            "id": r["id"], "warehouse_id": r["warehouse_id"], "lot_id": zn(r["lot_id"]),
            "status": r["status"], "temperature": to_decimal(r["temperature"]),
            "min_temp": to_decimal(r["min_temp"]), "max_temp": to_decimal(r["max_temp"]),
            "action_taken": r["action_taken"],
        } for r in self._query(sql, params)]
