"""Update customer use case."""

from __future__ import annotations

from backend.application.commands.customer_commands import UpdateCustomerCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class UpdateCustomerUseCase(DelegatingUseCase[UpdateCustomerCommand]):
    name = "UpdateCustomerUseCase"
