"""PrintRouteResolverPort — SET-12 "Routing". Distinct from
`repository_ports.py` (persistence) and `rendering_ports.py`
(bytes-out): this is the contract a wiring-layer adapter over
`device_management`'s `print_routing_policy.resolve_route()` +
`select_device()` implements — Document Output never imports
device_management types directly, the same bounded-context independence
`rendering_ports.py`/`hardware_ports.py` already established.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.document_output.value_objects.route_resolution import RouteResolution


class PrintRouteResolverPort(Protocol):
    def resolve(
        self, document_type: str, *, branch_id: str | None = None, workstation_id: str | None = None,
        module: str | None = None, channel: str | None = None,
    ) -> RouteResolution:
        """Resolve which route/device a document_type prints to in this
        context. Must raise rather than return a partial/placeholder
        result when nothing matches — the caller
        (`policies/ticket_routing_policy.py::create_routed_print_job`)
        does not catch or paper over a resolution failure."""
        ...
