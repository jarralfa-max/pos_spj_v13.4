"""Read model contract for Transfers navigation badges.

The desktop sidebar receives this DTO; it never calculates KPIs or reads a
repository/database itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TransferNavigationBadges:
    pending_requests: int = 0
    pending_approvals: int = 0
    ready_to_dispatch: int = 0
    in_transit: int = 0
    pending_receipts: int = 0
    open_differences: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "pending_requests": self.pending_requests,
            "pending_approvals": self.pending_approvals,
            "ready_to_dispatch": self.ready_to_dispatch,
            "in_transit": self.in_transit,
            "pending_receipts": self.pending_receipts,
            "open_differences": self.open_differences,
        }


class TransferNavigationReadPort(Protocol):
    def navigation_badges(self, *, user_id: str, branch_id: str | None) -> TransferNavigationBadges: ...


class TransferNavigationQueryService:
    def __init__(self, read_port: TransferNavigationReadPort) -> None:
        self._read_port = read_port

    def get_badges(self, *, user_id: str, branch_id: str | None) -> TransferNavigationBadges:
        """Return backend-scoped badge counts for the current session."""
        return self._read_port.navigation_badges(user_id=user_id, branch_id=branch_id)
