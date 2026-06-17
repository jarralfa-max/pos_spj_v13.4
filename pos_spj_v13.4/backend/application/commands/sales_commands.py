"""Sales module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreateSaleCommand(BaseCommand):
    items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    payment: Mapping[str, Any] = field(default_factory=dict)
    customer_id: str | None = None
    notes: str = ""
    reservation_id: str | None = None


@dataclass(frozen=True)
class CancelSaleCommand(BaseCommand):
    sale_id: str = ""
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.sale_id or "").strip():
            raise ValueError("sale_id is required")
        if not str(self.reason or "").strip():
            raise ValueError("reason is required")
