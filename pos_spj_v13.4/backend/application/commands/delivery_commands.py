"""Delivery module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreateDeliveryOrderCommand(BaseCommand):
    customer_id: str = ""
    address: str = ""
    notes: str = ""


@dataclass(frozen=True)
class AssignDeliveryDriverCommand(BaseCommand):
    delivery_order_id: str = ""
    driver_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.delivery_order_id or "").strip():
            raise ValueError("delivery_order_id is required")
        if not str(self.driver_id or "").strip():
            raise ValueError("driver_id is required")


@dataclass(frozen=True)
class AdjustDeliveryWeightCommand(BaseCommand):
    delivery_order_id: str = ""
    new_weight_kg: float = 0.0
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.delivery_order_id or "").strip():
            raise ValueError("delivery_order_id is required")
        if float(self.new_weight_kg or 0.0) <= 0:
            raise ValueError("new_weight_kg must be greater than zero")
