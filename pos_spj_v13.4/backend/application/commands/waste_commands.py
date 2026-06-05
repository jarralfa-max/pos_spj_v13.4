"""Waste module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class RegisterWasteCommand(BaseCommand):
    """Command for the canonical waste registration route."""

    product_id: int | str = 0
    quantity: float = 0.0
    reason: str = ""
    notes: str = ""
    date: str | None = None
    unit: str | None = None
    manager_pin_authorized: bool = False

    def validate_context(self) -> None:
        super().validate_context()
