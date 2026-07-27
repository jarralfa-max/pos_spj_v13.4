"""Redeem loyalty points use case."""

from __future__ import annotations

from backend.application.commands.loyalty_commands import RedeemLoyaltyPointsCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class RedeemLoyaltyPointsUseCase(DelegatingUseCase[RedeemLoyaltyPointsCommand]):
    name = "RedeemLoyaltyPointsUseCase"
