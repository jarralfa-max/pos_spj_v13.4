"""DriverSettlementRepository (ORD-21). Never commits — the owning
UnitOfWork does.
"""

from __future__ import annotations

import json

from backend.domain.orders_delivery.enums import SettlementStatus
from backend.domain.orders_delivery.settlement import DriverSettlement
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


class DriverSettlementRepository(OrdersDeliveryRepositoryBase):
    def save(self, settlement: DriverSettlement) -> None:
        self._execute(
            """
            INSERT INTO driver_settlements (
                id, driver_id, branch_id, collection_ids_json, expected_total,
                collected_total, status, reviewed_by_user_id, approved_by_user_id,
                closed_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                reviewed_by_user_id=excluded.reviewed_by_user_id,
                approved_by_user_id=excluded.approved_by_user_id,
                closed_at=excluded.closed_at,
                updated_at=excluded.updated_at
            """,
            (
                settlement.id, settlement.driver_id, settlement.branch_id,
                json.dumps(list(settlement.collection_ids)),
                dec_str(settlement.expected_total), dec_str(settlement.collected_total),
                enum_value(settlement.status), settlement.reviewed_by_user_id,
                settlement.approved_by_user_id, settlement.closed_at,
                settlement.created_at, settlement.updated_at,
            ),
        )

    def get(self, settlement_id: str) -> DriverSettlement | None:
        row = self._query_one("SELECT * FROM driver_settlements WHERE id=?", (settlement_id,))
        return self._hydrate(row) if row else None

    def list_for_driver(self, driver_id: str) -> list[DriverSettlement]:
        rows = self._query(
            "SELECT * FROM driver_settlements WHERE driver_id=?", (driver_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> DriverSettlement:
        return DriverSettlement(
            id=row["id"], driver_id=row["driver_id"], branch_id=row["branch_id"],
            collection_ids=tuple(json.loads(row["collection_ids_json"] or "[]")),
            expected_total=to_decimal(row["expected_total"]),
            collected_total=to_decimal(row["collected_total"]),
            status=SettlementStatus(row["status"]),
            reviewed_by_user_id=row["reviewed_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], closed_at=row["closed_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
