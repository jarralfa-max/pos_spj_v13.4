"""Hardware operation ports for the Device Management bounded context —
SET-10. Distinct from `repository_ports.py` (persistence): these
Protocols are the contract a *real* infrastructure gateway
(`backend/infrastructure/hardware/`, a later SET — no serial/network I/O
code is written here) would implement to actually talk to a cash drawer
or payment terminal.

Scope is deliberately narrow: `CashDrawerGatewayPort` only opens/queries
a drawer; `PaymentTerminalGatewayPort` only reports readiness. Processing
an actual card transaction (amount, currency, authorization) is Finance/
Sales' domain, not Device Management's — this port is not where that
belongs.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.device_management.value_objects.cash_drawer_open_request import CashDrawerOpenRequest


class CashDrawerGatewayPort(Protocol):
    def open(self, request: CashDrawerOpenRequest) -> bool:
        """Pulse the drawer open. Returns whether the pulse was sent —
        callers must not assume physical success, only that the command
        was issued (drawers have no reliable "did it open" sensor)."""
        ...

    def is_open(self, device_id: str) -> bool: ...


class PaymentTerminalGatewayPort(Protocol):
    def is_ready(self, device_id: str) -> bool:
        """Whether the terminal is connected and idle (no transaction in
        flight). Not a payment API — see this module's docstring."""
        ...
