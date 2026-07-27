"""Canonical use case shell for GeneratePurchasePlanUseCase."""

from __future__ import annotations

from backend.application.commands.purchase_planning_commands import GeneratePurchasePlanCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class GeneratePurchasePlanUseCase(DelegatingUseCase[GeneratePurchasePlanCommand]):
    name = "GeneratePurchasePlanUseCase"
