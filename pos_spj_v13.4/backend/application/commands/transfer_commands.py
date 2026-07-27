"""Transfer module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class TransferItem:
    """Immutable line item carried by transfer commands."""

    product_id: Any       # int (legacy schema) or str (future UUID)
    quantity_sent: float
    unit: str = "kg"
    notes: str = ""


@dataclass(frozen=True)
class DispatchTransferCommand(BaseCommand):
    """Command to dispatch a transfer from one branch to another (Phase 1)."""

    origin_branch_id: int = 0
    dest_branch_id: int = 0
    items: tuple[TransferItem, ...] = field(default_factory=tuple)
    dispatched_by: str = ""
    origin_type: str = "BRANCH"
    destination_type: str = "BRANCH"
    observations: str = ""


@dataclass(frozen=True)
class ReceiveTransferItem:
    """Actual quantity received for one transfer line."""

    product_id: Any
    quantity_received: float
    notes: str = ""


@dataclass(frozen=True)
class ReceiveTransferCommand(BaseCommand):
    """Command to receive a dispatched transfer (Phase 2)."""

    transfer_id: str = ""
    received_by: str = ""
    received_items: tuple[ReceiveTransferItem, ...] = field(default_factory=tuple)
    observations: str = ""


@dataclass(frozen=True)
class CancelTransferCommand(BaseCommand):
    """Command to cancel a pending or dispatched transfer."""

    transfer_id: str = ""
    reason: str = ""
