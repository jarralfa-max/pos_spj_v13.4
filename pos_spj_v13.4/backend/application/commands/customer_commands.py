"""Customer module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class UpdateCustomerCommand(BaseCommand):
    customer_id: str = ""
    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.customer_id or "").strip():
            raise ValueError("customer_id is required")
