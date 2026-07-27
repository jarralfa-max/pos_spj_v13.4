"""Approve quote use case."""

from __future__ import annotations

from backend.application.commands.quote_commands import ApproveQuoteCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ApproveQuoteUseCase(DelegatingUseCase[ApproveQuoteCommand]):
    name = "ApproveQuoteUseCase"
