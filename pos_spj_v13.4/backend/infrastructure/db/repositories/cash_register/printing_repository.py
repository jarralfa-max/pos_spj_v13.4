"""Born-clean persistence for Cash Register print queue and audit."""

from __future__ import annotations

import json
from typing import Any

from backend.application.cash_register.printing import (
    CashPrintArtifact,
    CashPrintDocumentType,
    CashPrintJob,
    PrintCashDocumentCommand,
)
from backend.shared.ids import new_uuid


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class CashPrintRepository:
    """Implements CashPrintQueue and CashPrintAuditRepository on the clean schema."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def enqueue(self, job: CashPrintJob) -> None:
        self.connection.execute(
            """INSERT INTO cash_print_jobs
            (id,operation_id,printer_id,document_type,entity_id,branch_id,
             output_format,media_type,filename,content,copies,status,
             original_print_id,metadata_json,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED',?,?,CURRENT_TIMESTAMP)""",
            (
                job.print_id,
                job.operation_id,
                job.printer_id,
                job.document_type.value,
                job.entity_id,
                job.branch_id,
                job.artifact.format.value,
                job.artifact.media_type,
                job.artifact.filename,
                job.artifact.content,
                job.copies,
                job.original_print_id,
                _json(job.metadata),
            ),
        )

    def print_id_for_operation(self, operation_id: str) -> str | None:
        cursor = self.connection.execute(
            """SELECT id FROM cash_print_jobs WHERE operation_id=?
            UNION
            SELECT print_id FROM cash_print_audit WHERE operation_id=?
            LIMIT 1""",
            (operation_id, operation_id),
        )
        row = cursor.fetchone()
        return None if row is None else row[0]

    def original_exists(self, print_id: str, entity_id: str,
                        document_type: CashPrintDocumentType) -> bool:
        cursor = self.connection.execute(
            """SELECT 1 FROM cash_print_jobs
            WHERE id=? AND entity_id=? AND document_type=?
              AND status IN ('QUEUED','PRINTED')
            LIMIT 1""",
            (print_id, entity_id, document_type.value),
        )
        return cursor.fetchone() is not None

    def record(self, *, print_id: str, command: PrintCashDocumentCommand,
               artifact: CashPrintArtifact, status: str,
               event_payload: dict[str, object]) -> None:
        self.connection.execute(
            """INSERT INTO cash_print_audit
            (id,print_id,operation_id,actor_user_id,branch_id,entity_id,
             document_type,output_format,printer_id,copies,status,
             original_print_id,reprint_reason,event_payload_json,artifact_filename,
             occurred_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (
                new_uuid(),
                print_id,
                command.operation_id,
                command.actor_user_id,
                command.document.branch_id,
                command.document.entity_id,
                command.document.document_type.value,
                artifact.format.value,
                command.printer_id,
                command.copies,
                status,
                command.original_print_id,
                command.reprint_reason,
                _json(event_payload),
                artifact.filename,
            ),
        )
        self.connection.execute(
            "UPDATE cash_print_jobs SET status=? WHERE id=?",
            (status, print_id),
        )

    def list_pending(self, *, branch_id: str, limit: int = 50) -> list[dict[str, object]]:
        cursor = self.connection.execute(
            """SELECT * FROM cash_print_jobs
            WHERE branch_id=? AND status IN ('QUEUED','RETRY')
            ORDER BY created_at,id LIMIT ?""",
            (branch_id, limit),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
