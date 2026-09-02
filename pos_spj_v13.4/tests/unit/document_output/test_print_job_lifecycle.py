"""SET-11 — PrintJob state machine + create_reprint(). Pure domain — no DB."""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobPriority, PrintJobStatus
from backend.domain.document_output.exceptions import (
    DocumentInvalidValueError,
    DocumentReprintNotAllowedError,
    PrintJobTransitionNotAllowedError,
)
from backend.shared.ids import is_uuidv7, new_uuid


def _job(**overrides) -> PrintJob:
    kwargs = dict(
        document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
        template_version_id=new_uuid(), requested_by_user_id="cashier-1",
    )
    kwargs.update(overrides)
    return PrintJob.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_normalizes_document_type_and_defaults(self):
        job = _job(document_type="sale_ticket")
        assert is_uuidv7(job.id)
        assert job.document_type == "SALE_TICKET"
        assert job.status is PrintJobStatus.PENDING
        assert job.priority is PrintJobPriority.NORMAL
        assert job.copies == 1
        assert job.retry_count == 0

    def test_requires_document_type(self):
        with pytest.raises(DocumentInvalidValueError):
            _job(document_type="   ")

    def test_requires_source_module(self):
        with pytest.raises(DocumentInvalidValueError):
            _job(source_module="   ")

    def test_requires_requested_by_user_id(self):
        with pytest.raises(DocumentInvalidValueError):
            _job(requested_by_user_id="")

    @pytest.mark.parametrize("copies", [0, -1, 1.5, True])
    def test_rejects_invalid_copies(self, copies):
        with pytest.raises(DocumentInvalidValueError):
            _job(copies=copies)

    def test_validates_source_document_id_and_template_version_id_as_uuid(self):
        with pytest.raises(ValueError):
            _job(source_document_id="not-a-uuid")
        with pytest.raises(ValueError):
            _job(template_version_id="not-a-uuid")


class TestFullHappyPath:
    def test_pending_to_printed(self):
        job = _job()
        job.start_rendering()
        assert job.status is PrintJobStatus.RENDERING

        job.mark_ready()
        assert job.status is PrintJobStatus.READY
        assert job.rendered_at is not None

        job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
        job.start_printing()
        assert job.status is PrintJobStatus.PRINTING

        job.mark_printed()
        assert job.status is PrintJobStatus.PRINTED
        assert job.printed_at is not None


class TestStartPrintingGuard:
    def test_cannot_print_without_printer_device_id(self):
        job = _job()
        job.start_rendering()
        job.mark_ready()
        with pytest.raises(PrintJobTransitionNotAllowedError):
            job.start_printing()

    def test_can_print_once_route_assigned(self):
        job = _job()
        job.start_rendering()
        job.mark_ready()
        job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
        job.start_printing()
        assert job.status is PrintJobStatus.PRINTING


class TestFailCancelRetryDeadLetter:
    def test_fail_from_rendering(self):
        job = _job()
        job.start_rendering()
        job.fail("Impresora sin papel")
        assert job.status is PrintJobStatus.FAILED
        assert job.failure_reason == "Impresora sin papel"

    def test_fail_from_printing(self):
        job = _job()
        job.start_rendering()
        job.mark_ready()
        job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
        job.start_printing()
        job.fail("Impresora desconectada")
        assert job.status is PrintJobStatus.FAILED

    def test_fail_requires_reason(self):
        job = _job()
        job.start_rendering()
        with pytest.raises(DocumentInvalidValueError):
            job.fail("   ")

    def test_fail_not_allowed_from_pending(self):
        job = _job()
        with pytest.raises(PrintJobTransitionNotAllowedError):
            job.fail("motivo")

    @pytest.mark.parametrize("terminal_state_setup", ["pending", "rendering", "ready"])
    def test_cancel_allowed_from_pending_rendering_ready(self, terminal_state_setup):
        job = _job()
        if terminal_state_setup in ("rendering", "ready"):
            job.start_rendering()
        if terminal_state_setup == "ready":
            job.mark_ready()
        job.cancel()
        assert job.status is PrintJobStatus.CANCELLED

    def test_cancel_not_allowed_once_printing(self):
        job = _job()
        job.start_rendering()
        job.mark_ready()
        job.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
        job.start_printing()
        with pytest.raises(PrintJobTransitionNotAllowedError):
            job.cancel()

    def test_retry_returns_to_pending_and_increments_count_clears_reason(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        job.retry()
        assert job.status is PrintJobStatus.PENDING
        assert job.retry_count == 1
        assert job.failure_reason is None

    def test_retry_not_allowed_unless_failed(self):
        job = _job()
        with pytest.raises(PrintJobTransitionNotAllowedError):
            job.retry()

    def test_move_to_dead_letter_requires_failed(self):
        job = _job()
        with pytest.raises(PrintJobTransitionNotAllowedError):
            job.move_to_dead_letter()

    def test_move_to_dead_letter_from_failed(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        job.move_to_dead_letter()
        assert job.status is PrintJobStatus.DEAD_LETTER


class TestCreateReprint:
    def test_requires_reason(self):
        job = _job()
        with pytest.raises(DocumentReprintNotAllowedError):
            job.create_reprint(requested_by_user_id="cashier-2", reason="   ")

    def test_creates_new_job_chained_to_original(self):
        original = _job(priority=PrintJobPriority.HIGH)
        reprint = original.create_reprint(requested_by_user_id="cashier-2", reason="Cliente perdió el ticket")
        assert reprint.id != original.id
        assert reprint.reprint_of_job_id == original.id
        assert reprint.reprint_reason == "Cliente perdió el ticket"
        assert reprint.status is PrintJobStatus.PENDING
        assert reprint.document_type == original.document_type
        assert reprint.source_document_id == original.source_document_id
        assert reprint.template_version_id == original.template_version_id
        assert reprint.priority == original.priority
        assert reprint.requested_by_user_id == "cashier-2"

    def test_reprint_can_be_requested_regardless_of_original_status(self):
        original = _job()
        original.start_rendering()
        original.mark_ready()
        original.assign_route(print_route_id=new_uuid(), printer_device_id=new_uuid())
        original.start_printing()
        original.mark_printed()
        reprint = original.create_reprint(requested_by_user_id="cashier-2", reason="Reimpresión solicitada")
        assert reprint.status is PrintJobStatus.PENDING
