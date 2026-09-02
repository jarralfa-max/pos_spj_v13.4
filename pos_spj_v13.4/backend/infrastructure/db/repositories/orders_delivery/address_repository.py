"""OrderAddressRepository — persists/reconstructs `OrderAddress` against the
`order_addresses` table (ORD-7). Never commits — the owning UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.address import OrderAddress
from backend.domain.orders_delivery.enums import GeocodingStatus
from backend.infrastructure.db.repositories.orders_delivery.base import OrdersDeliveryRepositoryBase


class OrderAddressRepository(OrdersDeliveryRepositoryBase):
    def save(self, address: OrderAddress) -> None:
        self._execute(
            """
            INSERT INTO order_addresses (
                id, order_id, recipient_name, recipient_phone, street, exterior_number,
                interior_number, neighborhood, postal_code, municipality, state,
                "references", latitude, longitude, geocoding_status, delivery_zone_id,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                recipient_name=excluded.recipient_name,
                recipient_phone=excluded.recipient_phone,
                street=excluded.street,
                exterior_number=excluded.exterior_number,
                interior_number=excluded.interior_number,
                neighborhood=excluded.neighborhood,
                postal_code=excluded.postal_code,
                municipality=excluded.municipality,
                state=excluded.state,
                "references"=excluded."references",
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                geocoding_status=excluded.geocoding_status,
                delivery_zone_id=excluded.delivery_zone_id,
                updated_at=excluded.updated_at
            """,
            (
                address.id, address.order_id, address.recipient_name, address.recipient_phone,
                address.street, address.exterior_number, address.interior_number,
                address.neighborhood, address.postal_code, address.municipality, address.state,
                address.references, address.latitude, address.longitude,
                address.geocoding_status.value, address.delivery_zone_id,
                address.created_at, address.updated_at,
            ),
        )

    def get_by_order_id(self, order_id: str) -> OrderAddress | None:
        row = self._query_one("SELECT * FROM order_addresses WHERE order_id=?", (order_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> OrderAddress:
        return OrderAddress(
            id=row["id"], order_id=row["order_id"], recipient_name=row["recipient_name"],
            recipient_phone=row["recipient_phone"], street=row["street"],
            exterior_number=row["exterior_number"], interior_number=row["interior_number"],
            neighborhood=row["neighborhood"], postal_code=row["postal_code"],
            municipality=row["municipality"], state=row["state"],
            references=row["references"], latitude=row["latitude"], longitude=row["longitude"],
            geocoding_status=GeocodingStatus(row["geocoding_status"]),
            delivery_zone_id=row["delivery_zone_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
