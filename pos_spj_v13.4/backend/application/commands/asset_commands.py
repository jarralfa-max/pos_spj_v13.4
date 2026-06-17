"""Asset module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreateAssetCommand(BaseCommand):
    name: str = ""
    category: str = ""
    serial_number: str = ""
    branch_id: str = ""
    acquisition_date: str = ""
    acquisition_cost: float = 0.0
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.name or "").strip():
            raise ValueError("name is required")


@dataclass(frozen=True)
class ScheduleMaintenanceCommand(BaseCommand):
    asset_id: str = ""
    scheduled_date: str = ""
    description: str = ""
    technician: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.asset_id or "").strip():
            raise ValueError("asset_id is required")
        if not str(self.scheduled_date or "").strip():
            raise ValueError("scheduled_date is required")


@dataclass(frozen=True)
class CompleteMaintenanceCommand(BaseCommand):
    maintenance_id: str = ""
    completion_date: str = ""
    cost: float = 0.0
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.maintenance_id or "").strip():
            raise ValueError("maintenance_id is required")
