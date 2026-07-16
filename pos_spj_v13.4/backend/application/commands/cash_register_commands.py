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
    employee_id: str | None = None


@dataclass(frozen=True)
class CloseCashShiftCommand(BaseCommand):
    shift_id: str | None = None
    z_cut_id: str | None = None
    cash_difference: float = 0.0
    counted_cash: float = 0.0
    notes: str = ""
    employee_id: str | None = None


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
