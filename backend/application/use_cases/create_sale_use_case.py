"""Canonical use case shell for CreateSaleUseCase."""

from __future__ import annotations

from backend.application.commands.sales_commands import CreateSaleCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CreateSaleUseCase(DelegatingUseCase[CreateSaleCommand]):
    name = "CreateSaleUseCase"
