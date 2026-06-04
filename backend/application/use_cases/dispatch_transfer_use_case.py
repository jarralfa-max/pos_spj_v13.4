"""Canonical use case shell for DispatchTransferUseCase."""

from __future__ import annotations

from backend.application.commands.transfer_commands import DispatchTransferCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class DispatchTransferUseCase(DelegatingUseCase[DispatchTransferCommand]):
    name = "DispatchTransferUseCase"
