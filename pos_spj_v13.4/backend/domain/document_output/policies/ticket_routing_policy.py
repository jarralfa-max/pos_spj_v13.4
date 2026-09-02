"""TicketRoutingPolicy — SET-12 "Routing": composes `PrintJob.create()`
with a `PrintRouteResolverPort` resolution + `assign_route()` as one
guarded operation, so a caller never ends up with a `PrintJob` that was
created but never routed. Mirrors the shape
`tests/unit/device_management/test_hardware_ports_composition.py::
_open_drawer_use_case` proved for gateways — policy first, port second —
but as a real named policy function, since Routing is an explicit SET-12
deliverable rather than a port-composition proof.
"""

from __future__ import annotations

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobPriority
from backend.domain.document_output.routing_ports import PrintRouteResolverPort


def create_routed_print_job(
    resolver: PrintRouteResolverPort, *, document_type: str, source_module: str,
    source_document_id: str, template_version_id: str, requested_by_user_id: str, copies: int = 1,
    priority: PrintJobPriority = PrintJobPriority.NORMAL, branch_id: str | None = None,
    workstation_id: str | None = None, module: str | None = None, channel: str | None = None,
) -> PrintJob:
    job = PrintJob.create(
        document_type=document_type, source_module=source_module, source_document_id=source_document_id,
        template_version_id=template_version_id, requested_by_user_id=requested_by_user_id, copies=copies,
        priority=priority,
    )
    resolution = resolver.resolve(
        job.document_type, branch_id=branch_id, workstation_id=workstation_id, module=module, channel=channel,
    )
    job.assign_route(print_route_id=resolution.print_route_id, printer_device_id=resolution.printer_device_id)
    return job
