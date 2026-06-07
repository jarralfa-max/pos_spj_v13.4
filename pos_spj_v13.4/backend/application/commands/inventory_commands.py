"""Inventory commands for the canonical application-service route."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class RegisterInventoryEntryCommand(BaseCommand):
    """Register an audited stock entry for one product and branch."""

    product_id: int = 0
    quantity: float = 0.0
    unit_cost: float = 0.0
    supplier_id: int | None = None
    reference: str = ""
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if self.product_id <= 0:
            raise ValueError("product_id is required")
        if int(self.branch_id) <= 0:
            raise ValueError("branch_id is required")
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if not self.user_name:
            raise ValueError("user_name is required")


@dataclass(frozen=True)
class AdjustInventoryCommand(BaseCommand):
    """Set audited physical-count stock for one product and branch."""

    product_id: int = 0
    new_quantity: float = 0.0
    reason: str = "Ajuste manual"

    def validate_context(self) -> None:
        super().validate_context()
        if self.product_id <= 0:
            raise ValueError("product_id is required")
        if int(self.branch_id) <= 0:
            raise ValueError("branch_id is required")
        if self.new_quantity < 0:
            raise ValueError("new_quantity cannot be negative")
        if not self.user_name:
            raise ValueError("user_name is required")
