"""Register cash movement use case."""

from __future__ import annotations

from backend.application.commands.cash_register_commands import RegisterCashMovementCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class RegisterCashMovementUseCase(DelegatingUseCase[RegisterCashMovementCommand]):
    name = "RegisterCashMovementUseCase"
