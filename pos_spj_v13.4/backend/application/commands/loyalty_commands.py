"""Loyalty module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class AssignLoyaltyCardCommand(BaseCommand):
    customer_id: str = ""
    card_code: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.customer_id or "").strip():
            raise ValueError("customer_id is required")
        if not str(self.card_code or "").strip():
            raise ValueError("card_code is required")


@dataclass(frozen=True)
class RedeemLoyaltyPointsCommand(BaseCommand):
    customer_id: str = ""
    points: int = 0
    sale_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.customer_id or "").strip():
            raise ValueError("customer_id is required")
        if int(self.points or 0) <= 0:
            raise ValueError("points must be greater than zero")
