"""Purchase module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreatePurchaseOrderCommand(BaseCommand):
    supplier_id: str = ""
    items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.supplier_id or "").strip():
            raise ValueError("supplier_id is required")


@dataclass(frozen=True)
class ReceivePurchaseCommand(BaseCommand):
    purchase_order_id: str = ""
    received_items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.purchase_order_id or "").strip():
            raise ValueError("purchase_order_id is required")
