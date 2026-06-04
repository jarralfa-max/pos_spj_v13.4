"""Canonical use case shell for ReceiveTransferUseCase."""

from __future__ import annotations

from backend.application.commands.transfer_commands import ReceiveTransferCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class ReceiveTransferUseCase(DelegatingUseCase[ReceiveTransferCommand]):
    name = "ReceiveTransferUseCase"
