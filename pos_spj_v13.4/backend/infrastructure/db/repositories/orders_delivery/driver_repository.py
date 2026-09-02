"""DriverOperationalProfileRepository / DeliveryAssignmentRepository (ORD-16).
Never commit — the owning UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.driver import DeliveryAssignment, DriverOperationalProfile
from backend.domain.orders_delivery.enums import AssignmentStatus
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


class DriverOperationalProfileRepository(OrdersDeliveryRepositoryBase):
    def save(self, profile: DriverOperationalProfile) -> None:
        self._execute(
            """
            INSERT INTO driver_operational_profiles (
                id, driver_id, branch_id, vehicle_type, active, capacity,
                current_assignment_count, cash_limit, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                vehicle_type=excluded.vehicle_type,
                active=excluded.active,
                capacity=excluded.capacity,
                current_assignment_count=excluded.current_assignment_count,
                cash_limit=excluded.cash_limit,
                updated_at=excluded.updated_at
            """,
            (
                profile.id, profile.driver_id, profile.branch_id, profile.vehicle_type,
                1 if profile.active else 0, profile.capacity,
                profile.current_assignment_count, dec_str(profile.cash_limit),
                profile.created_at, profile.updated_at,
            ),
        )

    def get_by_driver_id(self, driver_id: str) -> DriverOperationalProfile | None:
        row = self._query_one(
            "SELECT * FROM driver_operational_profiles WHERE driver_id=?", (driver_id,))
        return self._hydrate(row) if row else None

    def list_available_for_branch(self, branch_id: str) -> list[DriverOperationalProfile]:
        rows = self._query(
            "SELECT * FROM driver_operational_profiles WHERE branch_id=? AND active=1",
            (branch_id,))
        return [p for p in (self._hydrate(row) for row in rows) if p.has_capacity]

    @staticmethod
    def _hydrate(row: dict) -> DriverOperationalProfile:
        return DriverOperationalProfile(
            id=row["id"], driver_id=row["driver_id"], branch_id=row["branch_id"],
            vehicle_type=row["vehicle_type"], active=bool(row["active"]),
            capacity=row["capacity"], current_assignment_count=row["current_assignment_count"],
            cash_limit=to_decimal(row["cash_limit"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


class DeliveryAssignmentRepository(OrdersDeliveryRepositoryBase):
    def save(self, assignment: DeliveryAssignment) -> None:
        self._execute(
            """
            INSERT INTO delivery_assignments (
                id, delivery_job_id, driver_id, assigned_by_user_id, vehicle_id,
                status, assigned_at, accepted_at, released_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                accepted_at=excluded.accepted_at,
                released_at=excluded.released_at,
                updated_at=excluded.updated_at
            """,
            (
                assignment.id, assignment.delivery_job_id, assignment.driver_id,
                assignment.assigned_by_user_id, assignment.vehicle_id,
                enum_value(assignment.status), assignment.assigned_at,
                assignment.accepted_at, assignment.released_at, assignment.updated_at,
            ),
        )

    def get(self, assignment_id: str) -> DeliveryAssignment | None:
        row = self._query_one("SELECT * FROM delivery_assignments WHERE id=?", (assignment_id,))
        return self._hydrate(row) if row else None

    def list_for_job(self, delivery_job_id: str) -> list[DeliveryAssignment]:
        rows = self._query(
            "SELECT * FROM delivery_assignments WHERE delivery_job_id=? ORDER BY assigned_at",
            (delivery_job_id,))
        return [self._hydrate(row) for row in rows]

    def list_pending_for_driver(self, driver_id: str) -> list[DeliveryAssignment]:
        """ORD-25: the driver PWA's own "assignments awaiting my response"
        list — a genuine gap until now (every prior consumer looked up
        assignments by job, never by driver)."""
        rows = self._query(
            "SELECT * FROM delivery_assignments WHERE driver_id=? AND status=?"
            " ORDER BY assigned_at", (driver_id, enum_value(AssignmentStatus.PROPOSED)))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> DeliveryAssignment:
        return DeliveryAssignment(
            id=row["id"], delivery_job_id=row["delivery_job_id"], driver_id=row["driver_id"],
            assigned_by_user_id=row["assigned_by_user_id"], vehicle_id=row["vehicle_id"],
            status=AssignmentStatus(row["status"]), assigned_at=row["assigned_at"],
            accepted_at=row["accepted_at"], released_at=row["released_at"],
            updated_at=row["updated_at"],
        )
