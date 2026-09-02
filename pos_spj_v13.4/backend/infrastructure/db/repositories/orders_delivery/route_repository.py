"""DeliveryRouteRepository — persists/reconstructs `DeliveryRoute` (with its
`DeliveryRouteStop`s) against `delivery_routes`/`delivery_route_stops`
(ORD-17). `save()` replaces all of a route's stops wholesale, same
delete-then-reinsert shape as `CustomerOrderRepository.save()`. Never
commits — the owning UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import RouteStatus, RouteStopStatus
from backend.domain.orders_delivery.route import DeliveryRoute, DeliveryRouteStop
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    enum_value,
)


class DeliveryRouteRepository(OrdersDeliveryRepositoryBase):
    def save(self, route: DeliveryRoute) -> None:
        self._execute(
            """
            INSERT INTO delivery_routes (
                id, branch_id, status, assigned_driver_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                assigned_driver_id=excluded.assigned_driver_id,
                updated_at=excluded.updated_at
            """,
            (route.id, route.branch_id, enum_value(route.status), route.assigned_driver_id,
             route.created_at, route.updated_at),
        )
        self._execute("DELETE FROM delivery_route_stops WHERE route_id=?", (route.id,))
        for stop in route.stops:
            self._execute(
                """
                INSERT INTO delivery_route_stops (
                    id, route_id, delivery_job_id, sequence, status, estimated_arrival_at,
                    created_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (stop.id, stop.route_id, stop.delivery_job_id, stop.sequence,
                 enum_value(stop.status), stop.estimated_arrival_at, stop.created_at),
            )

    def get(self, route_id: str) -> DeliveryRoute | None:
        row = self._query_one("SELECT * FROM delivery_routes WHERE id=?", (route_id,))
        return self._hydrate(row) if row else None

    def _hydrate(self, row: dict) -> DeliveryRoute:
        stop_rows = self._query(
            "SELECT * FROM delivery_route_stops WHERE route_id=? ORDER BY sequence",
            (row["id"],))
        stops = [
            DeliveryRouteStop(
                id=r["id"], route_id=r["route_id"], delivery_job_id=r["delivery_job_id"],
                sequence=r["sequence"], status=RouteStopStatus(r["status"]),
                estimated_arrival_at=r["estimated_arrival_at"], created_at=r["created_at"],
            )
            for r in stop_rows
        ]
        return DeliveryRoute(
            id=row["id"], branch_id=row["branch_id"], status=RouteStatus(row["status"]),
            assigned_driver_id=row["assigned_driver_id"], stops=stops,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
