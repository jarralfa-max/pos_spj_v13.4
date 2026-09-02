"""DeliveryZoneRepository — persists/reconstructs `DeliveryZone` against the
`delivery_zones` table (ORD-7). Never commits — the owning UnitOfWork does.
"""

from __future__ import annotations

import json

from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    opt_dec_str,
    to_decimal,
)


class DeliveryZoneRepository(OrdersDeliveryRepositoryBase):
    def save(self, zone: DeliveryZone) -> None:
        self._execute(
            """
            INSERT INTO delivery_zones (
                id, branch_id, name, postal_codes_json, minimum_order, delivery_fee,
                free_delivery_threshold, estimated_minutes, maximum_distance_km, active,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                postal_codes_json=excluded.postal_codes_json,
                minimum_order=excluded.minimum_order,
                delivery_fee=excluded.delivery_fee,
                free_delivery_threshold=excluded.free_delivery_threshold,
                estimated_minutes=excluded.estimated_minutes,
                maximum_distance_km=excluded.maximum_distance_km,
                active=excluded.active,
                updated_at=excluded.updated_at
            """,
            (
                zone.id, zone.branch_id, zone.name,
                json.dumps(list(zone.postal_codes)),
                str(zone.minimum_order), str(zone.delivery_fee),
                opt_dec_str(zone.free_delivery_threshold),
                zone.estimated_minutes, opt_dec_str(zone.maximum_distance_km),
                1 if zone.active else 0, zone.created_at, zone.updated_at,
            ),
        )

    def list_active_for_branch(self, branch_id: str) -> list[DeliveryZone]:
        rows = self._query(
            "SELECT * FROM delivery_zones WHERE branch_id=? AND active=1", (branch_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> DeliveryZone:
        return DeliveryZone(
            id=row["id"], branch_id=row["branch_id"], name=row["name"],
            postal_codes=tuple(json.loads(row["postal_codes_json"] or "[]")),
            minimum_order=to_decimal(row["minimum_order"]),
            delivery_fee=to_decimal(row["delivery_fee"]),
            free_delivery_threshold=(
                to_decimal(row["free_delivery_threshold"])
                if row["free_delivery_threshold"] is not None else None),
            estimated_minutes=row["estimated_minutes"],
            maximum_distance_km=(
                to_decimal(row["maximum_distance_km"])
                if row["maximum_distance_km"] is not None else None),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
