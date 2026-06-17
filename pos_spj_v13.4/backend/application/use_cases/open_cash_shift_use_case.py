"""Open cash shift use case."""

from __future__ import annotations

from backend.application.commands.cash_register_commands import OpenCashShiftCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class OpenCashShiftUseCase(DelegatingUseCase[OpenCashShiftCommand]):
    name = "OpenCashShiftUseCase"
