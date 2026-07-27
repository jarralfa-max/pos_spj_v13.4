"""Receive purchase use case."""

from __future__ import annotations

from backend.application.commands.purchase_commands import ReceivePurchaseCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ReceivePurchaseUseCase(DelegatingUseCase[ReceivePurchaseCommand]):
    name = "ReceivePurchaseUseCase"
