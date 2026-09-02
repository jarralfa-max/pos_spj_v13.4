"""SqliteAdvertisingSlotRepository — persists `AdvertisingSlot` (SET-18).
Implements
`backend.domain.customer_display.repository_ports.AdvertisingSlotRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.advertising_slot import AdvertisingSlot
from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = "id, code, mode, display_order, active, created_at, updated_at"


class SqliteAdvertisingSlotRepository(CustomerDisplayRepositoryBase):
    def save(self, slot: AdvertisingSlot) -> None:
        self._execute(
            f"INSERT INTO advertising_slots ({_COLS})"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " display_order=excluded.display_order, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(slot),
        )

    def get(self, slot_id: str) -> AdvertisingSlot | None:
        row = self._query_one(f"SELECT {_COLS} FROM advertising_slots WHERE id=?", (slot_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> AdvertisingSlot | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM advertising_slots WHERE code=?", (code.strip().upper(),),
        )
        return self._hydrate(row) if row else None

    def list_by_mode(self, mode: CustomerDisplayMode) -> list[AdvertisingSlot]:
        rows = self._query(
            f"SELECT {_COLS} FROM advertising_slots WHERE mode=? ORDER BY display_order", (mode.value,),
        )
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[AdvertisingSlot]:
        rows = self._query(f"SELECT {_COLS} FROM advertising_slots ORDER BY mode, display_order")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(slot: AdvertisingSlot) -> tuple:
        return (
            slot.id, slot.code, slot.mode.value, slot.display_order, int(slot.active), slot.created_at,
            slot.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> AdvertisingSlot:
        return AdvertisingSlot(
            id=row["id"], code=row["code"], mode=CustomerDisplayMode(row["mode"]),
            display_order=row["display_order"], active=bool(row["active"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
