"""SET-12 — "Reimpresión": reprint_policy.assert_reprintable/request_reprint.
Pure domain — no DB. Distinct from
tests/unit/document_output/test_print_job_lifecycle.py::TestCreateReprint,
which covers the unconditional entity-level `create_reprint()` — these
tests cover the stricter, state-gated policy built on top of it.
"""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobStatus
from backend.domain.document_output.exceptions import DocumentReprintNotAllowedError
from backend.domain.document_output.policies.reprint_policy import assert_reprintable, request_reprint
from backend.shared.ids import new_uuid


def _job() -> PrintJob:
    return PrintJob.create(
        document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
        template_version_id=new_uuid(), requested_by_user_id="cashier-1",
    )


def _printed_job() -> PrintJob:
    job = _job()
    job.start_rendering()
    job.mark_ready()
    job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
    job.start_printing()
    job.mark_printed()
    return job


class TestAssertReprintable:
    @pytest.mark.parametrize("setup", ["pending", "rendering", "ready", "printing"])
    def test_rejects_in_flight_states(self, setup):
        job = _job()
        if setup in ("rendering", "ready", "printing"):
            job.start_rendering()
        if setup in ("ready", "printing"):
            job.mark_ready()
        if setup == "printing":
            job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
            job.start_printing()
        with pytest.raises(DocumentReprintNotAllowedError):
            assert_reprintable(job)

    def test_allows_printed(self):
        assert_reprintable(_printed_job())  # does not raise

    def test_allows_failed(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        assert_reprintable(job)  # does not raise

    def test_allows_dead_letter(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        job.move_to_dead_letter()
        assert_reprintable(job)  # does not raise

    def test_allows_cancelled(self):
        job = _job()
        job.cancel()
        assert_reprintable(job)  # does not raise


class TestRequestReprint:
    def test_returns_chained_reprint_for_printed_job(self):
        original = _printed_job()
        reprint = request_reprint(original, requested_by_user_id="cashier-2", reason="Ticket dañado")
        assert reprint.reprint_of_job_id == original.id
        assert reprint.reprint_reason == "Ticket dañado"
        assert reprint.status is PrintJobStatus.PENDING

    def test_rejects_reprint_of_in_flight_job(self):
        job = _job()
        job.start_rendering()
        with pytest.raises(DocumentReprintNotAllowedError):
            request_reprint(job, requested_by_user_id="cashier-2", reason="motivo")

    def test_still_requires_a_reason(self):
        original = _printed_job()
        with pytest.raises(DocumentReprintNotAllowedError):
            request_reprint(original, requested_by_user_id="cashier-2", reason="   ")
