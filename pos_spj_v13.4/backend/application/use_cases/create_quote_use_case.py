"""Create quote use case."""

from __future__ import annotations

from backend.application.commands.quote_commands import CreateQuoteCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CreateQuoteUseCase(DelegatingUseCase[CreateQuoteCommand]):
    name = "CreateQuoteUseCase"
