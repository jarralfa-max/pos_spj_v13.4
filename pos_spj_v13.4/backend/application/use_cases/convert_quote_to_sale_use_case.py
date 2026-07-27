"""Canonical use case shell for ConvertQuoteToSaleUseCase."""

from __future__ import annotations

from backend.application.commands.quote_commands import ConvertQuoteToSaleCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ConvertQuoteToSaleUseCase(DelegatingUseCase[ConvertQuoteToSaleCommand]):
    name = "ConvertQuoteToSaleUseCase"
