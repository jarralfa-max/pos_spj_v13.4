"""DeliveryJobRepository — persists/reconstructs `DeliveryJob` against the
`delivery_jobs` table (ORD-15). Never commits — the owning UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.delivery_job import DeliveryAttempt, DeliveryJob
from backend.domain.orders_delivery.enums import DeliveryStatus
from backend.domain.orders_delivery.policies.delivery_lifecycle_policy import (
    DeliveryLifecyclePolicy,
)
from backend.domain.orders_delivery.value_objects.delivery_evidence import DeliveryEvidence
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


class DeliveryJobRepository(OrdersDeliveryRepositoryBase):
    def save(self, job: DeliveryJob) -> None:
        self._execute(
            """
            INSERT INTO delivery_jobs (
                id, order_id, branch_id, delivery_number, delivery_zone_id, status,
                priority, assigned_driver_id, route_id,
                scheduled_window_start, scheduled_window_end, estimated_arrival_at,
                dispatched_at, delivered_at, failed_at,
                delivery_fee, cash_to_collect, payment_method_expected,
                operation_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                delivery_number=excluded.delivery_number,
                delivery_zone_id=excluded.delivery_zone_id,
                status=excluded.status,
                priority=excluded.priority,
                assigned_driver_id=excluded.assigned_driver_id,
                route_id=excluded.route_id,
                scheduled_window_start=excluded.scheduled_window_start,
                scheduled_window_end=excluded.scheduled_window_end,
                estimated_arrival_at=excluded.estimated_arrival_at,
                dispatched_at=excluded.dispatched_at,
                delivered_at=excluded.delivered_at,
                failed_at=excluded.failed_at,
                delivery_fee=excluded.delivery_fee,
                cash_to_collect=excluded.cash_to_collect,
                payment_method_expected=excluded.payment_method_expected,
                updated_at=excluded.updated_at
            """,
            (
                job.id, job.order_id, job.branch_id, job.delivery_number,
                job.delivery_zone_id, enum_value(job.status), job.priority,
                job.assigned_driver_id, job.route_id,
                job.scheduled_window_start, job.scheduled_window_end,
                job.estimated_arrival_at, job.dispatched_at, job.delivered_at, job.failed_at,
                dec_str(job.delivery_fee), dec_str(job.cash_to_collect),
                job.payment_method_expected, job.operation_id,
                job.created_at, job.updated_at,
            ),
        )
        self._execute("DELETE FROM delivery_attempts WHERE delivery_job_id=?", (job.id,))
        for attempt in job.attempts:
            evidence = attempt.evidence
            self._execute(
                """
                INSERT INTO delivery_attempts (
                    id, delivery_job_id, successful, recipient_name, signature_reference,
                    photo_reference, pin_verified, latitude, longitude, evidence_notes,
                    failure_reason, attempted_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    attempt.id, attempt.delivery_job_id, 1 if attempt.successful else 0,
                    evidence.recipient_name if evidence else None,
                    evidence.signature_reference if evidence else None,
                    evidence.photo_reference if evidence else None,
                    1 if (evidence and evidence.pin_verified) else 0,
                    evidence.latitude if evidence else None,
                    evidence.longitude if evidence else None,
                    evidence.notes if evidence else None,
                    attempt.failure_reason, attempt.attempted_at,
                ),
            )

    def get(self, job_id: str) -> DeliveryJob | None:
        row = self._query_one("SELECT * FROM delivery_jobs WHERE id=?", (job_id,))
        return self._hydrate(row) if row else None

    def get_by_order_id(self, order_id: str) -> DeliveryJob | None:
        row = self._query_one("SELECT * FROM delivery_jobs WHERE order_id=?", (order_id,))
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> DeliveryJob | None:
        row = self._query_one(
            "SELECT * FROM delivery_jobs WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def list_for_branch(self, branch_id: str, *, status: DeliveryStatus | None = None) -> list[DeliveryJob]:
        if status is not None:
            rows = self._query(
                "SELECT * FROM delivery_jobs WHERE branch_id=? AND status=?",
                (branch_id, enum_value(status)))
        else:
            rows = self._query("SELECT * FROM delivery_jobs WHERE branch_id=?", (branch_id,))
        return [self._hydrate(row) for row in rows]

    def list_for_driver(self, driver_id: str, *, active_only: bool = True) -> list[DeliveryJob]:
        """ORD-25: the driver PWA's own "my jobs" list — a genuine gap until
        now (every prior consumer queried by branch, never by the assigned
        driver)."""
        if active_only:
            final = tuple(v.value for v in DeliveryLifecyclePolicy.FINAL_STATUSES)
            placeholders = ",".join("?" * len(final))
            rows = self._query(
                f"SELECT * FROM delivery_jobs WHERE assigned_driver_id=?"
                f" AND status NOT IN ({placeholders}) ORDER BY created_at",
                (driver_id, *final))
        else:
            rows = self._query(
                "SELECT * FROM delivery_jobs WHERE assigned_driver_id=? ORDER BY created_at",
                (driver_id,))
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict) -> DeliveryJob:
        attempt_rows = self._query(
            "SELECT * FROM delivery_attempts WHERE delivery_job_id=? ORDER BY attempted_at",
            (row["id"],))
        attempts = [self._hydrate_attempt(r) for r in attempt_rows]
        return DeliveryJob(
            id=row["id"], order_id=row["order_id"], branch_id=row["branch_id"],
            delivery_number=row["delivery_number"], delivery_zone_id=row["delivery_zone_id"],
            status=DeliveryStatus(row["status"]), priority=row["priority"],
            assigned_driver_id=row["assigned_driver_id"], route_id=row["route_id"],
            scheduled_window_start=row["scheduled_window_start"],
            scheduled_window_end=row["scheduled_window_end"],
            estimated_arrival_at=row["estimated_arrival_at"],
            dispatched_at=row["dispatched_at"], delivered_at=row["delivered_at"],
            failed_at=row["failed_at"], delivery_fee=to_decimal(row["delivery_fee"]),
            cash_to_collect=to_decimal(row["cash_to_collect"]),
            payment_method_expected=row["payment_method_expected"],
            operation_id=row["operation_id"], attempts=attempts,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _hydrate_attempt(row: dict) -> DeliveryAttempt:
        evidence = None
        if any((row["recipient_name"], row["signature_reference"], row["photo_reference"],
                row["pin_verified"], row["latitude"] is not None, row["evidence_notes"])):
            evidence = DeliveryEvidence(
                recipient_name=row["recipient_name"],
                signature_reference=row["signature_reference"],
                photo_reference=row["photo_reference"],
                pin_verified=bool(row["pin_verified"]),
                latitude=row["latitude"], longitude=row["longitude"],
                notes=row["evidence_notes"],
            )
        return DeliveryAttempt(
            id=row["id"], delivery_job_id=row["delivery_job_id"],
            successful=bool(row["successful"]), evidence=evidence,
            failure_reason=row["failure_reason"], attempted_at=row["attempted_at"],
        )
