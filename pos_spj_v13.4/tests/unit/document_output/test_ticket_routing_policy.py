"""SET-12 — "Routing": PrintRouteResolverPort composition +
ticket_routing_policy.create_routed_print_job(). Pure domain — no DB, no
device_management import (bounded-context independence, same as
rendering_ports.py/test_rendering_ports_composition.py).
"""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobPriority
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.policies.ticket_routing_policy import create_routed_print_job
from backend.domain.document_output.routing_ports import PrintRouteResolverPort
from backend.domain.document_output.value_objects.route_resolution import RouteResolution
from backend.shared.ids import is_uuidv7, new_uuid


class _FakeResolver:
    """Satisfies PrintRouteResolverPort structurally — no real device_management."""

    def __init__(self, *, resolution: RouteResolution | None = None) -> None:
        self.resolution = resolution or RouteResolution.create(
            print_route_id=new_uuid(), printer_device_id=new_uuid(),
        )
        self.calls: list[dict] = []

    def resolve(
        self, document_type: str, *, branch_id=None, workstation_id=None, module=None, channel=None,
    ) -> RouteResolution:
        self.calls.append(
            {"document_type": document_type, "branch_id": branch_id, "workstation_id": workstation_id,
             "module": module, "channel": channel},
        )
        return self.resolution


class _FailingResolver:
    def resolve(self, document_type: str, **kwargs) -> RouteResolution:
        raise DocumentInvalidValueError("sin ruta disponible")


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
        template_version_id=new_uuid(), requested_by_user_id="cashier-1",
    )
    kwargs.update(overrides)
    return kwargs


class TestCreateRoutedPrintJob:
    def test_returns_a_fully_routed_print_job(self):
        resolver = _FakeResolver()
        job = create_routed_print_job(resolver, **_base_kwargs())
        assert isinstance(job, PrintJob)
        assert is_uuidv7(job.id)
        assert job.print_route_id == resolver.resolution.print_route_id
        assert job.printer_device_id == resolver.resolution.printer_device_id

    def test_resolver_receives_normalized_document_type_and_scope_context(self):
        resolver = _FakeResolver()
        branch_id, workstation_id = new_uuid(), new_uuid()
        create_routed_print_job(
            resolver, **_base_kwargs(document_type="sale_ticket"),
            branch_id=branch_id, workstation_id=workstation_id, module="sales", channel="pos",
        )
        assert resolver.calls == [
            {"document_type": "SALE_TICKET", "branch_id": branch_id, "workstation_id": workstation_id,
             "module": "sales", "channel": "pos"},
        ]

    def test_priority_and_copies_pass_through(self):
        resolver = _FakeResolver()
        job = create_routed_print_job(
            resolver, **_base_kwargs(priority=PrintJobPriority.URGENT, copies=3),
        )
        assert job.priority is PrintJobPriority.URGENT
        assert job.copies == 3

    def test_resolution_failure_propagates_and_job_is_never_returned(self):
        with pytest.raises(DocumentInvalidValueError):
            create_routed_print_job(_FailingResolver(), **_base_kwargs())
