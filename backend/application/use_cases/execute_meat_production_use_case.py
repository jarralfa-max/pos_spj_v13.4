"""Canonical use case shell for ExecuteMeatProductionUseCase."""

from __future__ import annotations

from backend.application.commands.production_commands import ExecuteMeatProductionCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ExecuteMeatProductionUseCase(DelegatingUseCase[ExecuteMeatProductionCommand]):
    name = "ExecuteMeatProductionUseCase"
