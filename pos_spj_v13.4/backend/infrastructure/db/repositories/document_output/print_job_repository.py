"""SqlitePrintJobRepository — persists `PrintJob` (SET-11). Implements
`backend.domain.document_output.repository_ports.PrintJobRepositoryPort`.
Mirrors backend/infrastructure/db/repositories/settings/configuration_value_repository.py:
`operation_id` is a persistence-only idempotency key, not a field on the
`PrintJob` entity itself — a caller passes it to `save()` once (e.g. the
sale-completion use case's own operation_id) so a retried call finds the
already-created job via `get_by_operation_id()` instead of duplicating it.
"""

from __future__ import annotations

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobPriority, PrintJobStatus
from backend.infrastructure.db.repositories.document_output.base import DocumentOutputRepositoryBase

_INSERT_COLS = (
    "id, document_type, source_module, source_document_id, template_version_id,"
    " requested_by_user_id, copies, priority, print_route_id, printer_device_id, status,"
    " requested_at, rendered_at, printed_at, failure_reason, retry_count, reprint_of_job_id,"
    " reprint_reason, operation_id, created_at, updated_at"
)

_SELECT_COLS = (
    "id, document_type, source_module, source_document_id, template_version_id,"
    " requested_by_user_id, copies, priority, print_route_id, printer_device_id, status,"
    " requested_at, rendered_at, printed_at, failure_reason, retry_count, reprint_of_job_id,"
    " reprint_reason, created_at, updated_at"
)


class SqlitePrintJobRepository(DocumentOutputRepositoryBase):
    def save(self, job: PrintJob, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO print_jobs ({_INSERT_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " priority=excluded.priority, print_route_id=excluded.print_route_id,"
            " printer_device_id=excluded.printer_device_id, status=excluded.status,"
            " rendered_at=excluded.rendered_at, printed_at=excluded.printed_at,"
            " failure_reason=excluded.failure_reason, retry_count=excluded.retry_count,"
            " operation_id=excluded.operation_id, updated_at=excluded.updated_at",
            self._params(job, operation_id),
        )

    def get(self, job_id: str) -> PrintJob | None:
        row = self._query_one(f"SELECT {_SELECT_COLS} FROM print_jobs WHERE id=?", (job_id,))
        return self._hydrate(row) if row else None

    def list_by_status(self, status: PrintJobStatus) -> list[PrintJob]:
        rows = self._query(
            f"SELECT {_SELECT_COLS} FROM print_jobs WHERE status=? ORDER BY requested_at", (status.value,),
        )
        return [self._hydrate(row) for row in rows]

    def get_by_operation_id(self, operation_id: str) -> PrintJob | None:
        row = self._query_one(
            f"SELECT {_SELECT_COLS} FROM print_jobs WHERE operation_id=?", (operation_id,),
        )
        return self._hydrate(row) if row else None

    def list_by_source(self, source_module: str, source_document_id: str) -> list[PrintJob]:
        # requested_at has only second-level precision, so two jobs for the
        # same source created within the same second would tie; id (UUIDv7,
        # lexicographically time-ordered) is a reliable secondary key.
        rows = self._query(
            f"SELECT {_SELECT_COLS} FROM print_jobs WHERE source_module=? AND source_document_id=?"
            " ORDER BY requested_at DESC, id DESC",
            (source_module, source_document_id),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(job: PrintJob, operation_id: str | None) -> tuple:
        return (
            job.id, job.document_type, job.source_module, job.source_document_id,
            job.template_version_id, job.requested_by_user_id, job.copies, job.priority.value,
            job.print_route_id, job.printer_device_id, job.status.value, job.requested_at,
            job.rendered_at, job.printed_at, job.failure_reason, job.retry_count,
            job.reprint_of_job_id, job.reprint_reason, operation_id, job.created_at, job.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> PrintJob:
        return PrintJob(
            id=row["id"], document_type=row["document_type"], source_module=row["source_module"],
            source_document_id=row["source_document_id"], template_version_id=row["template_version_id"],
            requested_by_user_id=row["requested_by_user_id"], copies=row["copies"],
            priority=PrintJobPriority(row["priority"]), print_route_id=row["print_route_id"],
            printer_device_id=row["printer_device_id"], status=PrintJobStatus(row["status"]),
            requested_at=row["requested_at"], rendered_at=row["rendered_at"],
            printed_at=row["printed_at"], failure_reason=row["failure_reason"],
            retry_count=row["retry_count"], reprint_of_job_id=row["reprint_of_job_id"],
            reprint_reason=row["reprint_reason"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
