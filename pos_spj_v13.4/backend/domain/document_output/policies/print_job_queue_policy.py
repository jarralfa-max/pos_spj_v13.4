"""PrintJobQueuePolicy — SET-11 "Worker": pure queue-selection and
retry-vs-give-up decisions. The actual background loop that dequeues,
renders, and sends jobs to a printer (`backend/infrastructure/printing/print_worker.py`
in the master prompt's own layout) is infrastructure — a later SET, not
domain logic. What belongs here is the *decision*: which PENDING job
goes next, and whether a FAILED job gets another attempt or is given up
on.
"""

from __future__ import annotations

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PRIORITY_ORDER, PrintJobStatus


def select_next_job(jobs: list[PrintJob]) -> PrintJob | None:
    """Most urgent priority first; oldest `requested_at` breaks ties
    within the same priority (FIFO)."""
    pending = [job for job in jobs if job.status is PrintJobStatus.PENDING]
    if not pending:
        return None
    return min(pending, key=lambda job: (PRIORITY_ORDER.index(job.priority), job.requested_at))


def should_retry(job: PrintJob, *, max_retries: int) -> bool:
    return job.status is PrintJobStatus.FAILED and job.retry_count < max_retries


def retry_or_dead_letter(job: PrintJob, *, max_retries: int) -> None:
    if should_retry(job, max_retries=max_retries):
        job.retry()
    else:
        job.move_to_dead_letter()
