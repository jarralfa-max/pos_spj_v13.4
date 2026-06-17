"""Cash register module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class GenerateZCutCommand(BaseCommand):
    pass


@dataclass(frozen=True)
class OpenCashShiftCommand(BaseCommand):
    opening_amount: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class RegisterCashMovementCommand(BaseCommand):
    movement_type: str = ""
    amount: float = 0.0
    concept: str = ""
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.movement_type or "").strip():
            raise ValueError("movement_type is required")
        if float(self.amount or 0.0) <= 0:
            raise ValueError("amount must be greater than zero")
