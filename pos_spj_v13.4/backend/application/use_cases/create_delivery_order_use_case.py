"""Canonical use case shell for CreateDeliveryOrderUseCase."""

from __future__ import annotations

from backend.application.commands.delivery_commands import CreateDeliveryOrderCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CreateDeliveryOrderUseCase(DelegatingUseCase[CreateDeliveryOrderCommand]):
    name = "CreateDeliveryOrderUseCase"
