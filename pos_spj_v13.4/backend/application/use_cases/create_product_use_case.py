"""Canonical use case shell for CreateProductUseCase."""

from __future__ import annotations

from backend.application.commands.product_commands import CreateProductCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CreateProductUseCase(DelegatingUseCase[CreateProductCommand]):
    name = "CreateProductUseCase"
