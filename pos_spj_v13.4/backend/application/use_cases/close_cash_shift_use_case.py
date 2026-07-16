"""Canonical use case shell for CloseCashShiftUseCase."""

from __future__ import annotations

from backend.application.commands.cash_register_commands import CloseCashShiftCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CloseCashShiftUseCase(DelegatingUseCase[CloseCashShiftCommand]):
    name = "CloseCashShiftUseCase"
