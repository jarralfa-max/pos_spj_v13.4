"""Assign delivery driver use case."""

from __future__ import annotations

from backend.application.commands.delivery_commands import AssignDeliveryDriverCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class AssignDeliveryDriverUseCase(DelegatingUseCase[AssignDeliveryDriverCommand]):
    name = "AssignDeliveryDriverUseCase"
