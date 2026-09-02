"""SqliteCustomerDisplayRepository — persists `CustomerDisplay` (SET-17).
Implements
`backend.domain.customer_display.repository_ports.CustomerDisplayRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.customer_display import CustomerDisplay
from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = "id, workstation_id, name, current_mode, active, created_at, updated_at"


class SqliteCustomerDisplayRepository(CustomerDisplayRepositoryBase):
    def save(self, display: CustomerDisplay) -> None:
        self._execute(
            f"INSERT INTO customer_displays ({_COLS})"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, current_mode=excluded.current_mode, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(display),
        )

    def get(self, display_id: str) -> CustomerDisplay | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_displays WHERE id=?", (display_id,))
        return self._hydrate(row) if row else None

    def list_by_workstation(self, workstation_id: str) -> list[CustomerDisplay]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_displays WHERE workstation_id=? ORDER BY name",
            (workstation_id,),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[CustomerDisplay]:
        rows = self._query(f"SELECT {_COLS} FROM customer_displays WHERE active=1 ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(display: CustomerDisplay) -> tuple:
        return (
            display.id, display.workstation_id, display.name, display.current_mode.value,
            int(display.active), display.created_at, display.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerDisplay:
        return CustomerDisplay(
            id=row["id"], workstation_id=row["workstation_id"], name=row["name"],
            current_mode=CustomerDisplayMode(row["current_mode"]), active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
