"""MaintenancePlan — preventive maintenance schedule for an asset (ASSET-6, §23).

Frequencies are enumerated (``MaintenanceFrequencyType``), never hardcoded
strings. ``estimated_cost`` is an evidence figure only — it is never posted
to Finance from here (see docs/refactor/assets_finance_boundary_map.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.assets.enums import (
    AssetCriticality,
    MaintenanceFrequencyType,
    MaintenancePlanStatus,
    MaintenanceType,
)
from backend.domain.assets.exceptions import AssetDomainError, MaintenanceStateInvalidError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MaintenancePlan:
    id: str
    asset_id: str
    maintenance_type: MaintenanceType
    frequency_type: MaintenanceFrequencyType
    operation_id: str
    frequency_value: int | None = None
    meter_trigger: str | None = None
    next_due_at: date | None = None
    priority: AssetCriticality = AssetCriticality.MEDIUM
    estimated_duration_minutes: int | None = None
    estimated_cost: Money | None = None
    assigned_team: str | None = None
    external_provider_id: str | None = None
    instructions: str = ""
    status: MaintenancePlanStatus = MaintenancePlanStatus.ACTIVE
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, maintenance_type: MaintenanceType,
               frequency_type: MaintenanceFrequencyType, operation_id: str,
               *, next_due_at: date | None = None, **extra) -> "MaintenancePlan":
        if not asset_id:
            raise AssetDomainError("MaintenancePlan.asset_id is required")
        if frequency_type is MaintenanceFrequencyType.CUSTOM and not extra.get("frequency_value"):
            raise AssetDomainError(
                "MaintenancePlan with CUSTOM frequency requires frequency_value")
        if frequency_type is MaintenanceFrequencyType.METER_BASED and not extra.get("meter_trigger"):
            raise AssetDomainError(
                "MaintenancePlan with METER_BASED frequency requires meter_trigger")
        return cls(
            id=new_uuid(), asset_id=asset_id, maintenance_type=maintenance_type,
            frequency_type=frequency_type, operation_id=operation_id,
            next_due_at=next_due_at, **extra,
        )

    def reschedule(self, next_due_at: date) -> None:
        if self.status is not MaintenancePlanStatus.ACTIVE:
            raise MaintenanceStateInvalidError(
                f"No se puede reprogramar un plan en estado {self.status.value}")
        self.next_due_at = next_due_at
        self.updated_at = _utcnow()

    def pause(self) -> None:
        if self.status is not MaintenancePlanStatus.ACTIVE:
            raise MaintenanceStateInvalidError(
                f"No se puede pausar un plan en estado {self.status.value}")
        self.status = MaintenancePlanStatus.PAUSED
        self.updated_at = _utcnow()

    def resume(self) -> None:
        if self.status is not MaintenancePlanStatus.PAUSED:
            raise MaintenanceStateInvalidError(
                f"No se puede reanudar un plan en estado {self.status.value}")
        self.status = MaintenancePlanStatus.ACTIVE
        self.updated_at = _utcnow()

    def deactivate(self) -> None:
        self.status = MaintenancePlanStatus.INACTIVE
        self.updated_at = _utcnow()
