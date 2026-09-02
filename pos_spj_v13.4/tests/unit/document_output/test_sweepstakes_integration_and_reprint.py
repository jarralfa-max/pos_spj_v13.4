"""SET-15 — "Integración con Sweepstakes", "Plantilla", "Reimpresión":
proves `SweepstakesTicketPort` composition with a fake adapter (mirroring
`test_rendering_ports_composition.py`'s pattern), that
`DocumentType.SWEEPSTAKES_TICKET` (already existed since SET-11) composes
end to end with the unchanged `DocumentTemplate`/`DocumentTemplateVersion`
lifecycle, and that SET-12's `reprint_policy` applies to a sweepstakes
`PrintJob` exactly like any other document type — no new template or
reprint code was needed, only the new `SweepstakesTicketData` DTO and
`SweepstakesTicketPort` contract. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import DocumentType, RenderFormat
from backend.domain.document_output.exceptions import DocumentReprintNotAllowedError
from backend.domain.document_output.policies.reprint_policy import assert_reprintable, request_reprint
from backend.domain.document_output.policies.template_activation_policy import activate_version
from backend.domain.document_output.sweepstakes_ports import SweepstakesTicketPort
from backend.domain.document_output.value_objects.sweepstakes_ticket_data import SweepstakesTicketData
from backend.shared.ids import new_uuid


class _FakeSweepstakesTicketPort:
    """Satisfies SweepstakesTicketPort structurally — no real LoyaltyService."""

    def __init__(self) -> None:
        self._tickets: dict[str, SweepstakesTicketData] = {}

    def register(self, ticket: SweepstakesTicketData) -> None:
        self._tickets[ticket.ticket_number] = ticket

    def get_ticket(self, ticket_number: str) -> SweepstakesTicketData:
        if ticket_number not in self._tickets:
            raise KeyError(f"No existe el boleto {ticket_number!r}")
        return self._tickets[ticket_number]


def _ticket(**overrides) -> SweepstakesTicketData:
    kwargs = dict(
        raffle_id=new_uuid(), raffle_name="Rifa de Verano", ticket_number="0001234",
        prize="Refrigerador", draw_date="2026-09-15",
    )
    kwargs.update(overrides)
    return SweepstakesTicketData.create(**kwargs)


class TestSweepstakesTicketPortComposition:
    def test_fake_port_returns_registered_ticket(self):
        port: SweepstakesTicketPort = _FakeSweepstakesTicketPort()
        ticket = _ticket()
        port.register(ticket)
        assert port.get_ticket("0001234") is ticket

    def test_unknown_ticket_number_raises(self):
        port: SweepstakesTicketPort = _FakeSweepstakesTicketPort()
        with pytest.raises(KeyError):
            port.get_ticket("does-not-exist")


class TestSweepstakesTemplateLifecycle:
    def test_sweepstakes_ticket_template_full_happy_path(self):
        template = DocumentTemplate.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET, name="Boleto de sorteo", module="loyalty",
        )
        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS,
            content="BOLETO {ticket_number} - {raffle_name}",
        )
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        activate_version(version, activated_by_user_id="admin-1")
        assert version.is_active()
        assert template.document_type is DocumentType.SWEEPSTAKES_TICKET


class TestSweepstakesReprintReusesReprintPolicyUnchanged:
    def _printed_sweepstakes_job(self) -> PrintJob:
        job = PrintJob.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET.value, source_module="loyalty",
            source_document_id=new_uuid(), template_version_id=new_uuid(), requested_by_user_id="op-1",
        )
        job.start_rendering()
        job.mark_ready()
        job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
        job.start_printing()
        job.mark_printed()
        return job

    def test_printed_sweepstakes_ticket_is_reprintable(self):
        job = self._printed_sweepstakes_job()
        assert_reprintable(job)  # does not raise
        reprint = request_reprint(job, requested_by_user_id="op-2", reason="Boleto extraviado")
        assert reprint.reprint_of_job_id == job.id
        assert reprint.document_type == "SWEEPSTAKES_TICKET"

    def test_in_flight_sweepstakes_job_is_not_reprintable(self):
        job = PrintJob.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET.value, source_module="loyalty",
            source_document_id=new_uuid(), template_version_id=new_uuid(), requested_by_user_id="op-1",
        )
        with pytest.raises(DocumentReprintNotAllowedError):
            request_reprint(job, requested_by_user_id="op-2", reason="motivo")
