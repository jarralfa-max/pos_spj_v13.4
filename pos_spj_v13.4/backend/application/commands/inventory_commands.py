"""Commands for canonical inventory use cases."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class RegisterInventoryMovementCommand(BaseCommand):
    product_id: int = 0
    quantity: float = 0.0
    unit: str = "unit"
    movement_type: str = ""
    source_module: str = "inventory"
    reference_type: str | None = None
    reference_id: str | None = None
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        _validate_product_id(self.product_id)
        _validate_branch_id(self.branch_id)
        _validate_positive_quantity(self.quantity)
        if not self.movement_type:
            raise ValueError("movement_type is required")
        if not self.source_module:
            raise ValueError("source_module is required")


@dataclass(frozen=True)
class RegisterInventoryEntryCommand(BaseCommand):
    """Canonical stock entry command used by inventory UI.

    This is not a legacy command: it maps to InventoryApplicationService.increase_stock
    and keeps UI code from constructing raw movement records.
    """

    product_id: int = 0
    quantity: float = 0.0
    unit: str = "unit"
    unit_cost: float = 0.0
    source_module: str = "inventory"
    reference_type: str | None = "inventory_entry"
    reference_id: str | None = None
    notes: str = ""
    reason: str = "Entrada de mercancía"

    def validate_context(self) -> None:
        super().validate_context()
        _validate_product_id(self.product_id)
        _validate_branch_id(self.branch_id)
        _validate_positive_quantity(self.quantity)
        if not self.source_module:
            raise ValueError("source_module is required")


@dataclass(frozen=True)
class AdjustInventoryCommand(BaseCommand):
    product_id: int = 0
    new_quantity: float = 0.0
    unit: str = "unit"
    source_module: str = "inventory"
    reference_type: str | None = None
    reference_id: str | None = None
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        _validate_product_id(self.product_id)
        _validate_branch_id(self.branch_id)
        if float(self.new_quantity) < 0:
            raise ValueError("new_quantity cannot be negative")
        if not self.source_module:
            raise ValueError("source_module is required")


@dataclass(frozen=True)
class TransferInventoryCommand(BaseCommand):
    product_id: int = 0
    from_branch_id: int = 0
    to_branch_id: int = 0
    quantity: float = 0.0
    unit: str = "unit"
    source_module: str = "inventory"
    reference_type: str | None = None
    reference_id: str | None = None
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        _validate_product_id(self.product_id)
        _validate_branch_id(self.from_branch_id)
        _validate_branch_id(self.to_branch_id)
        _validate_positive_quantity(self.quantity)
        if int(self.from_branch_id) == int(self.to_branch_id):
            raise ValueError("from_branch_id and to_branch_id must be different")
        if not self.source_module:
            raise ValueError("source_module is required")


def _validate_product_id(product_id: int) -> None:
    if int(product_id or 0) <= 0:
        raise ValueError("product_id is required")


def _validate_branch_id(branch_id: int | str) -> None:
    if int(branch_id or 0) <= 0:
        raise ValueError("branch_id is required")


def _validate_positive_quantity(quantity: float) -> None:
    if float(quantity or 0.0) <= 0:
        raise ValueError("quantity must be greater than zero")
