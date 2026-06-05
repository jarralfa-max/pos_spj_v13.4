"""Canonical use case shell for RegisterWasteUseCase."""

from __future__ import annotations

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class RegisterWasteUseCase(DelegatingUseCase[RegisterWasteCommand]):
    name = "RegisterWasteUseCase"
