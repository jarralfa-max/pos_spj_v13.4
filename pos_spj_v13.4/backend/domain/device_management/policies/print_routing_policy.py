"""PrintRoutingPolicy — SET-8 (§25): resolve which `PrintRoute` applies,
then pick a live printer from its primary→fallback chain.

`select_device` takes `is_available` as a plain callable rather than
reaching for a real health-check gateway itself — this keeps routing
pure/testable; the actual "is this printer online" answer comes from
infrastructure (a later SET's diagnostic gateway), not from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.exceptions import NoAvailablePrinterError, PrintRouteNotFoundError


@dataclass(frozen=True, slots=True)
class DeviceSelection:
    device_id: str
    used_failover: bool
    attempted_device_ids: tuple[str, ...]


def resolve_route(
    document_type: str, candidates: list[PrintRoute], *, branch_id: str | None = None,
    workstation_id: str | None = None, module: str | None = None, channel: str | None = None,
) -> PrintRoute:
    matching = [
        route for route in candidates
        if route.matches(document_type, branch_id=branch_id, workstation_id=workstation_id, module=module, channel=channel)
    ]
    if not matching:
        raise PrintRouteNotFoundError(
            f"No hay PrintRoute activa para document_type={document_type!r} en este contexto"
        )
    return max(matching, key=PrintRoute.specificity)


def select_device(route: PrintRoute, *, is_available: Callable[[str], bool]) -> DeviceSelection:
    chain = (route.primary_device_id, *route.fallback_device_ids)
    attempted: list[str] = []
    for index, device_id in enumerate(chain):
        attempted.append(device_id)
        if is_available(device_id):
            return DeviceSelection(
                device_id=device_id, used_failover=index > 0, attempted_device_ids=tuple(attempted),
            )
    raise NoAvailablePrinterError(
        f"Ningún dispositivo disponible para la ruta {route.document_type} "
        f"(intentados: {attempted})"
    )
