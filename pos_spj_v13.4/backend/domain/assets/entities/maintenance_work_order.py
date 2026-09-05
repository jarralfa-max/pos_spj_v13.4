"""MaintenanceWorkOrder — the operative unit of maintenance work (ASSET-6, §24-25).

State machine (§25):

    DRAFT -> REQUESTED -> APPROVED -> SCHEDULED -> ASSIGNED -> IN_PROGRESS
        IN_PROGRESS <-> PAUSED
        IN_PROGRESS -> WAITING_PARTS | WAITING_PROVIDER -> IN_PROGRESS
        IN_PROGRESS | WAITING_PARTS | WAITING_PROVIDER -> COMPLETED -> CLOSED
        any non-terminal -> CANCELLED

``complete()`` records ``actual_cost`` as evidence only — it never posts to
Finance/Treasury. The application layer (a later phase) is responsible for
publishing ``MAINTENANCE_COST_CONFIRMED`` after this call so Finance/AP can
decide OPEX vs CAPEX (docs/refactor/assets_finance_boundary_map.md, §29).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import (
    AssetCriticality,
    MaintenanceProviderType,
    MaintenanceType,
    MaintenanceWorkOrderStatus,
)
from backend.domain.assets.exceptions import AssetDomainError, MaintenanceStateInvalidError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid

_TERMINAL = frozenset({MaintenanceWorkOrderStatus.CLOSED, MaintenanceWorkOrderStatus.CANCELLED})
_ACTIVE_WORK_STATES = frozenset({
    MaintenanceWorkOrderStatus.IN_PROGRESS,
    MaintenanceWorkOrderStatus.WAITING_PARTS,
    MaintenanceWorkOrderStatus.WAITING_PROVIDER,
})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MaintenanceWorkOrder:
    id: str
    work_order_number: str
    asset_id: str
    maintenance_type: MaintenanceType
    operation_id: str
    maintenance_plan_id: str | None = None
    priority: AssetCriticality = AssetCriticality.MEDIUM
    status: MaintenanceWorkOrderStatus = MaintenanceWorkOrderStatus.DRAFT
    description: str = ""
    reported_issue: str = ""
    provider_type: MaintenanceProviderType = MaintenanceProviderType.INTERNAL
    scheduled_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    assigned_employee_id: str | None = None
    external_supplier_id: str | None = None
    estimated_cost: Money | None = None
    actual_cost: Money | None = None
    downtime_minutes: int | None = None
    resolution: str = ""
    root_cause: str = ""
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    version: int = 1
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, work_order_number: str, asset_id: str, maintenance_type: MaintenanceType,
               operation_id: str, *, created_by_user_id: str | None = None,
               **extra) -> "MaintenanceWorkOrder":
        if not work_order_number or not work_order_number.strip():
            raise AssetDomainError("MaintenanceWorkOrder.work_order_number is required")
        if not asset_id:
            raise AssetDomainError("MaintenanceWorkOrder.asset_id is required")
        return cls(
            id=new_uuid(), work_order_number=work_order_number.strip(), asset_id=asset_id,
            maintenance_type=maintenance_type, operation_id=operation_id,
            created_by_user_id=created_by_user_id, **extra,
        )

    def _assert_status(self, *allowed: MaintenanceWorkOrderStatus) -> None:
        if self.status not in allowed:
            raise MaintenanceStateInvalidError(
                f"No se puede continuar la orden de trabajo en estado {self.status.value}")

    def _touch(self) -> None:
        self.version += 1
        self.updated_at = _utcnow()

    def submit(self) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.DRAFT)
        self.status = MaintenanceWorkOrderStatus.REQUESTED
        self._touch()

    def approve(self, approved_by_user_id: str) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.REQUESTED)
        if not approved_by_user_id:
            raise AssetDomainError("MaintenanceWorkOrder.approve requires an approver")
        self.approved_by_user_id = approved_by_user_id
        self.status = MaintenanceWorkOrderStatus.APPROVED
        self._touch()

    def schedule(self, scheduled_at: str) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.APPROVED)
        self.scheduled_at = scheduled_at
        self.status = MaintenanceWorkOrderStatus.SCHEDULED
        self._touch()

    def assign(self, *, employee_id: str | None = None, supplier_id: str | None = None) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.SCHEDULED)
        if not employee_id and not supplier_id:
            raise AssetDomainError(
                "MaintenanceWorkOrder.assign requires an employee_id or supplier_id")
        self.assigned_employee_id = employee_id
        self.external_supplier_id = supplier_id
        self.provider_type = (
            MaintenanceProviderType.EXTERNAL if supplier_id else MaintenanceProviderType.INTERNAL
        )
        self.status = MaintenanceWorkOrderStatus.ASSIGNED
        self._touch()

    def start(self) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.ASSIGNED, MaintenanceWorkOrderStatus.PAUSED)
        self.status = MaintenanceWorkOrderStatus.IN_PROGRESS
        if self.started_at is None:
            self.started_at = _utcnow()
        self._touch()

    def pause(self) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.IN_PROGRESS)
        self.status = MaintenanceWorkOrderStatus.PAUSED
        self._touch()

    def wait_for_parts(self) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.IN_PROGRESS)
        self.status = MaintenanceWorkOrderStatus.WAITING_PARTS
        self._touch()

    def wait_for_provider(self) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.IN_PROGRESS)
        self.status = MaintenanceWorkOrderStatus.WAITING_PROVIDER
        self._touch()

    def resume_from_wait(self) -> None:
        self._assert_status(
            MaintenanceWorkOrderStatus.WAITING_PARTS, MaintenanceWorkOrderStatus.WAITING_PROVIDER)
        self.status = MaintenanceWorkOrderStatus.IN_PROGRESS
        self._touch()

    def complete(self, actual_cost: Money, resolution: str, *,
                 downtime_minutes: int | None = None, root_cause: str = "") -> None:
        if self.status not in _ACTIVE_WORK_STATES:
            raise MaintenanceStateInvalidError(
                f"No se puede completar una orden de trabajo en estado {self.status.value}")
        if not resolution or not resolution.strip():
            raise AssetDomainError("MaintenanceWorkOrder.complete requires a resolution")
        self.actual_cost = actual_cost
        self.resolution = resolution.strip()
        self.downtime_minutes = downtime_minutes
        self.root_cause = root_cause
        self.status = MaintenanceWorkOrderStatus.COMPLETED
        self.completed_at = _utcnow()
        self._touch()

    def close(self) -> None:
        self._assert_status(MaintenanceWorkOrderStatus.COMPLETED)
        self.status = MaintenanceWorkOrderStatus.CLOSED
        self._touch()

    def cancel(self, reason: str = "") -> None:
        if self.status in _TERMINAL:
            raise MaintenanceStateInvalidError(
                f"No se puede cancelar una orden de trabajo en estado {self.status.value}")
        self.status = MaintenanceWorkOrderStatus.CANCELLED
        if reason:
            self.resolution = f"{self.resolution}\n[CANCELLED] {reason}".strip()
        self._touch()
