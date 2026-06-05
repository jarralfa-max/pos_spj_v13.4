"""Canonical use case shell for GenerateZCutUseCase."""

from __future__ import annotations

from backend.application.commands.cash_register_commands import GenerateZCutCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class GenerateZCutUseCase(DelegatingUseCase[GenerateZCutCommand]):
    name = "GenerateZCutUseCase"
