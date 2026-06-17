"""Quote module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class ConvertQuoteToSaleCommand(BaseCommand):
    quote_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.quote_id or "").strip():
            raise ValueError("quote_id is required")


@dataclass(frozen=True)
class CreateQuoteCommand(BaseCommand):
    customer_id: str | None = None
    items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    notes: str = ""
    valid_days: int = 30


@dataclass(frozen=True)
class ApproveQuoteCommand(BaseCommand):
    quote_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.quote_id or "").strip():
            raise ValueError("quote_id is required")
