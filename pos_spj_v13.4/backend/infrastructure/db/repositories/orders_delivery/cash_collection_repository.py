"""DriverCashCollectionRepository (ORD-20). Never commits — the owning
UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.cash_collection import DriverCashCollection
from backend.domain.orders_delivery.enums import CollectionPaymentMethod, CollectionStatus
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


class DriverCashCollectionRepository(OrdersDeliveryRepositoryBase):
    def save(self, collection: DriverCashCollection) -> None:
        self._execute(
            """
            INSERT INTO driver_cash_collections (
                id, delivery_job_id, driver_id, expected_amount, payment_method,
                collected_amount, reference, status, collected_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                collected_amount=excluded.collected_amount,
                reference=excluded.reference,
                status=excluded.status,
                collected_at=excluded.collected_at,
                updated_at=excluded.updated_at
            """,
            (
                collection.id, collection.delivery_job_id, collection.driver_id,
                dec_str(collection.expected_amount), enum_value(collection.payment_method),
                dec_str(collection.collected_amount), collection.reference,
                enum_value(collection.status), collection.collected_at,
                collection.created_at, collection.updated_at,
            ),
        )

    def get(self, collection_id: str) -> DriverCashCollection | None:
        row = self._query_one(
            "SELECT * FROM driver_cash_collections WHERE id=?", (collection_id,))
        return self._hydrate(row) if row else None

    def get_by_job_id(self, delivery_job_id: str) -> DriverCashCollection | None:
        row = self._query_one(
            "SELECT * FROM driver_cash_collections WHERE delivery_job_id=?", (delivery_job_id,))
        return self._hydrate(row) if row else None

    def list_for_driver(self, driver_id: str, *,
                         status: CollectionStatus | None = None) -> list[DriverCashCollection]:
        if status is not None:
            rows = self._query(
                "SELECT * FROM driver_cash_collections WHERE driver_id=? AND status=?",
                (driver_id, enum_value(status)))
        else:
            rows = self._query(
                "SELECT * FROM driver_cash_collections WHERE driver_id=?", (driver_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> DriverCashCollection:
        return DriverCashCollection(
            id=row["id"], delivery_job_id=row["delivery_job_id"], driver_id=row["driver_id"],
            expected_amount=to_decimal(row["expected_amount"]),
            payment_method=CollectionPaymentMethod(row["payment_method"]),
            collected_amount=to_decimal(row["collected_amount"]), reference=row["reference"],
            status=CollectionStatus(row["status"]), collected_at=row["collected_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
