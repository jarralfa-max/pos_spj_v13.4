"""DocumentOutputPrintRoutingClient — Document Output's integration point
onto the real Device Management bounded context for print routing
(SET-12 "Routing"). Implements
`backend.domain.document_output.routing_ports.PrintRouteResolverPort`.

Mirrors `sales_cash_drawer_client.py`'s shape: thin, delegates entirely to
the real owning context's policy functions
(`device_management.policies.print_routing_policy.resolve_route`/
`select_device`, SET-8) and its real repositories
(`SqlitePrintRouteRepository.list_candidates`,
`SqliteDeviceRepository.get`), and — same as that client's own docstring
— "translates nothing except the failure boundary": `PrintRouteNotFoundError`/
`NoAvailablePrinterError` (device_management's own exceptions) propagate
to the caller unchanged, not wrapped into a document_output exception.

Unlike `rendering_ports.DocumentRendererPort` (SET-11, no real
implementation — generating real ESC/POS/PDF output needs a real
library/vendor target) and `hardware_ports.py` (SET-10, no real
implementation — needs real serial/network I/O), routing resolution is
pure logic plus SQLite reads: no external dependency is needed to build
and validate a real adapter, so this one is real, not a stub.
"""

from __future__ import annotations

from backend.domain.device_management.enums import DeviceStatus
from backend.domain.device_management.policies.print_routing_policy import resolve_route, select_device
from backend.domain.document_output.value_objects.route_resolution import RouteResolution
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)


class DocumentOutputPrintRoutingClient:
    def __init__(self, route_repo: SqlitePrintRouteRepository, device_repo: SqliteDeviceRepository) -> None:
        self._route_repo = route_repo
        self._device_repo = device_repo

    def resolve(
        self, document_type: str, *, branch_id: str | None = None, workstation_id: str | None = None,
        module: str | None = None, channel: str | None = None,
    ) -> RouteResolution:
        candidates = self._route_repo.list_candidates(document_type)
        route = resolve_route(
            document_type, candidates, branch_id=branch_id, workstation_id=workstation_id,
            module=module, channel=channel,
        )
        selection = select_device(route, is_available=self._is_device_active)
        return RouteResolution.create(print_route_id=route.id, printer_device_id=selection.device_id)

    def _is_device_active(self, device_id: str) -> bool:
        device = self._device_repo.get(device_id)
        return device is not None and device.status is DeviceStatus.ACTIVE
