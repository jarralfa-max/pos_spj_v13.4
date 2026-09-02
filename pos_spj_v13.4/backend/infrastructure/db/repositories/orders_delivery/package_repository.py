"""OrderPackageRepository — persists/reconstructs `OrderPackage` against the
`order_packages` table (ORD-13). Never commits — the owning UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import PackageStatus, PackageType
from backend.domain.orders_delivery.package import OrderPackage
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    opt_dec_str,
    to_decimal,
)


class OrderPackageRepository(OrdersDeliveryRepositoryBase):
    def save(self, package: OrderPackage) -> None:
        self._execute(
            """
            INSERT INTO order_packages (
                id, order_id, package_number, package_type, tare, gross_weight,
                temperature, seal_number, status, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                tare=excluded.tare,
                gross_weight=excluded.gross_weight,
                temperature=excluded.temperature,
                seal_number=excluded.seal_number,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                package.id, package.order_id, package.package_number,
                enum_value(package.package_type), dec_str(package.tare),
                dec_str(package.gross_weight), opt_dec_str(package.temperature),
                package.seal_number, enum_value(package.status),
                package.created_at, package.updated_at,
            ),
        )

    def get(self, package_id: str) -> OrderPackage | None:
        row = self._query_one("SELECT * FROM order_packages WHERE id=?", (package_id,))
        return self._hydrate(row) if row else None

    def list_for_order(self, order_id: str) -> list[OrderPackage]:
        rows = self._query(
            "SELECT * FROM order_packages WHERE order_id=? ORDER BY created_at", (order_id,))
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict) -> OrderPackage:
        line_ids = tuple(
            r["id"] for r in self._query(
                "SELECT id FROM customer_order_lines WHERE package_id=?", (row["id"],))
        )
        return OrderPackage(
            id=row["id"], order_id=row["order_id"], package_number=row["package_number"],
            package_type=PackageType(row["package_type"]), line_ids=line_ids,
            tare=to_decimal(row["tare"]), gross_weight=to_decimal(row["gross_weight"]),
            temperature=(to_decimal(row["temperature"]) if row["temperature"] is not None else None),
            seal_number=row["seal_number"], status=PackageStatus(row["status"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
