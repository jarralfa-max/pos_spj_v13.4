"""Schedule maintenance use case."""

from __future__ import annotations

from backend.application.commands.asset_commands import ScheduleMaintenanceCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ScheduleMaintenanceUseCase(DelegatingUseCase[ScheduleMaintenanceCommand]):
    name = "ScheduleMaintenanceUseCase"
