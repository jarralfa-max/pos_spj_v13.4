"""Adjust delivery weight use case."""

from __future__ import annotations

from backend.application.commands.delivery_commands import AdjustDeliveryWeightCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class AdjustDeliveryWeightUseCase(DelegatingUseCase[AdjustDeliveryWeightCommand]):
    name = "AdjustDeliveryWeightUseCase"
