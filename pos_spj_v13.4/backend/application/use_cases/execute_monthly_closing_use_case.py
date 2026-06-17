"""Execute monthly closing use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import ExecuteMonthlyClosingCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ExecuteMonthlyClosingUseCase(DelegatingUseCase[ExecuteMonthlyClosingCommand]):
    name = "ExecuteMonthlyClosingUseCase"
