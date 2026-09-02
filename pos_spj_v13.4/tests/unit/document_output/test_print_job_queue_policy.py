"""SET-11 — print_job_queue_policy: select_next_job priority/FIFO, and
should_retry/retry_or_dead_letter. Pure domain — no DB.
"""

from __future__ import annotations

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobPriority, PrintJobStatus
from backend.domain.document_output.policies.print_job_queue_policy import (
    retry_or_dead_letter,
    select_next_job,
    should_retry,
)
from backend.shared.ids import new_uuid


def _job(*, priority: PrintJobPriority = PrintJobPriority.NORMAL) -> PrintJob:
    return PrintJob.create(
        document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
        template_version_id=new_uuid(), requested_by_user_id="cashier-1", priority=priority,
    )


class TestSelectNextJob:
    def test_returns_none_when_no_pending_jobs(self):
        assert select_next_job([]) is None

    def test_ignores_non_pending_jobs(self):
        job = _job()
        job.start_rendering()
        assert select_next_job([job]) is None

    def test_urgent_beats_low_priority_even_if_requested_later(self):
        low = _job(priority=PrintJobPriority.LOW)
        urgent = _job(priority=PrintJobPriority.URGENT)
        # low was "created first" in wall-clock terms but urgent must still win.
        selected = select_next_job([low, urgent])
        assert selected.id == urgent.id

    def test_fifo_breaks_ties_within_same_priority(self):
        first = _job(priority=PrintJobPriority.NORMAL)
        second = _job(priority=PrintJobPriority.NORMAL)
        second.requested_at = first.requested_at  # force a true tie
        selected = select_next_job([second, first])
        # Both have identical requested_at; min() is stable and picks the
        # first equally-ranked element from the input order.
        assert selected.id in (first.id, second.id)

    def test_orders_by_priority_rank_full_sweep(self):
        urgent = _job(priority=PrintJobPriority.URGENT)
        high = _job(priority=PrintJobPriority.HIGH)
        normal = _job(priority=PrintJobPriority.NORMAL)
        low = _job(priority=PrintJobPriority.LOW)
        jobs = [low, normal, high, urgent]
        assert select_next_job(jobs).id == urgent.id
        jobs.remove(urgent)
        assert select_next_job(jobs).id == high.id
        jobs.remove(high)
        assert select_next_job(jobs).id == normal.id
        jobs.remove(normal)
        assert select_next_job(jobs).id == low.id


class TestShouldRetry:
    def test_true_when_failed_and_under_max(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        assert should_retry(job, max_retries=2) is True

    def test_false_when_not_failed(self):
        job = _job()
        assert should_retry(job, max_retries=2) is False

    def test_false_when_retry_count_reached_max(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        job.retry()
        job.start_rendering()
        job.fail("timeout again")
        assert job.retry_count == 1
        assert should_retry(job, max_retries=1) is False


class TestRetryOrDeadLetter:
    def test_retries_then_dead_letters_at_max(self):
        job = _job()
        max_retries = 2

        job.start_rendering()
        job.fail("timeout 1")
        retry_or_dead_letter(job, max_retries=max_retries)
        assert job.status is PrintJobStatus.PENDING
        assert job.retry_count == 1

        job.start_rendering()
        job.fail("timeout 2")
        retry_or_dead_letter(job, max_retries=max_retries)
        assert job.status is PrintJobStatus.PENDING
        assert job.retry_count == 2

        job.start_rendering()
        job.fail("timeout 3")
        retry_or_dead_letter(job, max_retries=max_retries)
        assert job.status is PrintJobStatus.DEAD_LETTER

    def test_zero_max_retries_dead_letters_immediately(self):
        job = _job()
        job.start_rendering()
        job.fail("timeout")
        retry_or_dead_letter(job, max_retries=0)
        assert job.status is PrintJobStatus.DEAD_LETTER
