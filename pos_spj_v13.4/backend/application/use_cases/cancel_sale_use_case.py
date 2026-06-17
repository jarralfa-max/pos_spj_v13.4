"""Cancel sale use case."""

from __future__ import annotations

from backend.application.commands.sales_commands import CancelSaleCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CancelSaleUseCase(DelegatingUseCase[CancelSaleCommand]):
    name = "CancelSaleUseCase"
