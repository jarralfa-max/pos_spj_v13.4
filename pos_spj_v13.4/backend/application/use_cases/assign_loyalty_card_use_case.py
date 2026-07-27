"""Assign loyalty card use case."""

from __future__ import annotations

from backend.application.commands.loyalty_commands import AssignLoyaltyCardCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class AssignLoyaltyCardUseCase(DelegatingUseCase[AssignLoyaltyCardCommand]):
    name = "AssignLoyaltyCardUseCase"
