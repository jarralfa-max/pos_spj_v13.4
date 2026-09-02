"""RouteResolution — SET-12 "Routing": the outcome of asking "which
printer should this document_type go to, in this context?" — a plain
(print_route_id, printer_device_id) pair. `PrintRoute`/`resolve_route()`/
`select_device()` (device_management, SET-8) already answer that
question; this bounded context never imports them directly (same
cross-context independence discipline as everywhere else in this
refactor) — `routing_ports.py::PrintRouteResolverPort` is the seam a
wiring layer bridges with a real adapter over `resolve_route()` +
`select_device()`.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class RouteResolution:
    print_route_id: str
    printer_device_id: str

    @classmethod
    def create(cls, *, print_route_id: str, printer_device_id: str) -> "RouteResolution":
        return cls(
            print_route_id=validate_uuidv7(print_route_id),
            printer_device_id=validate_uuidv7(printer_device_id),
        )
