"""CustomerDisplayGatewayPort — SET-17 "Gateway": the outbound port that
would push resolved screen content to a real physical/virtual customer
display. Mirrors `backend.domain.device_management.hardware_ports.py`
(SET-10) and `backend.domain.document_output.rendering_ports.
DocumentRendererPort` (SET-11): a pure Protocol, no real implementation.

**No real implementation here, on purpose** — SET-0's own audit of this
codebase found "no real customer-display consumer/hardware exists
anywhere in this repository (confirmed by research — zero references)".
Building a push mechanism to a device that doesn't exist would be the
exact decorative infrastructure
`backend/application/sales/queries/customer_display_query_service.py`'s
own docstring already refused to build for the same reason. A future
consumer implements this port once real hardware (or even just a real
second-screen web view) exists to validate against.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.customer_display.enums import CustomerDisplayMode


class CustomerDisplayGatewayPort(Protocol):
    def push(self, *, display_id: str, mode: CustomerDisplayMode, content: dict) -> None:
        """Push the resolved, section-filtered content for `mode` to the
        display identified by `display_id`. Must raise rather than
        silently drop content the display can't currently accept — the
        caller (a future use case) decides how to handle that failure,
        the same discipline `rendering_ports.DocumentRendererPort.render()`
        already documents."""
        ...
