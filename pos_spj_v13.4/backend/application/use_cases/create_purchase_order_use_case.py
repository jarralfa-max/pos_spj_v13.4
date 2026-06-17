"""Create purchase order use case."""

from __future__ import annotations

from backend.application.commands.purchase_commands import CreatePurchaseOrderCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CreatePurchaseOrderUseCase(DelegatingUseCase[CreatePurchaseOrderCommand]):
    name = "CreatePurchaseOrderUseCase"
