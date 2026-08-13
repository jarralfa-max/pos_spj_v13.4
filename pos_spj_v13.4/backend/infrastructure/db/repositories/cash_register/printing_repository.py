"""Born-clean persistence for Cash Register print queue and audit."""

from __future__ import annotations

import json
from typing import Any

from backend.application.cash_register.printing import (
    CashPrintArtifact,
    CashPrintDocumentType,
    CashPrintJob,
    CashQueuedPrintJob,
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
              AND status IN ('QUEUED','PRINTED','FAILED','RETRY')
            LIMIT 1""",
            (print_id, entity_id, document_type.value),
        )
        return cursor.fetchone() is not None

    def latest_print_id_for_document(self, *, entity_id: str,
                                     document_type: CashPrintDocumentType) -> str | None:
        cursor = self.connection.execute(
            """SELECT id FROM cash_print_jobs
            WHERE entity_id=? AND document_type=? AND status IN ('QUEUED','PRINTED','FAILED','RETRY')
            ORDER BY created_at DESC,id DESC LIMIT 1""",
            (entity_id, document_type.value),
        )
        row = cursor.fetchone()
        return None if row is None else str(row[0])

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

    def list_pending_jobs(self, *, branch_id: str,
                          limit: int = 25) -> tuple[CashQueuedPrintJob, ...]:
        cursor = self.connection.execute(
            """SELECT id,printer_id,content,media_type,filename,copies
            FROM cash_print_jobs
            WHERE branch_id=? AND status IN ('QUEUED','RETRY')
            ORDER BY created_at,id LIMIT ?""",
            (branch_id, limit),
        )
        return tuple(
            CashQueuedPrintJob(
                print_id=str(row[0]),
                printer_id=str(row[1]),
                content=bytes(row[2]),
                media_type=str(row[3]),
                filename=str(row[4]),
                copies=int(row[5]),
            )
            for row in cursor.fetchall()
        )

    def mark_printed(self, *, print_id: str, actor_user_id: str,
                     gateway_reference: str | None = None) -> None:
        self._record_delivery_status(
            print_id=print_id,
            actor_user_id=actor_user_id,
            status="PRINTED",
            last_error=None,
            gateway_reference=gateway_reference,
        )

    def mark_failed(self, *, print_id: str, actor_user_id: str, error: str) -> None:
        self._record_delivery_status(
            print_id=print_id,
            actor_user_id=actor_user_id,
            status="FAILED",
            last_error=error or "Print gateway failed",
            gateway_reference=None,
        )

    def _record_delivery_status(self, *, print_id: str, actor_user_id: str,
                                status: str, last_error: str | None,
                                gateway_reference: str | None) -> None:
        row = self.connection.execute(
            """SELECT operation_id,branch_id,entity_id,document_type,output_format,
                      printer_id,copies,original_print_id,filename
            FROM cash_print_jobs WHERE id=?""",
            (print_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Cash print job not found")
        (
            original_operation_id,
            branch_id,
            entity_id,
            document_type,
            output_format,
            printer_id,
            copies,
            original_print_id,
            filename,
        ) = row
        self.connection.execute(
            """UPDATE cash_print_jobs
            SET status=?,
                printed_at=CASE WHEN ?='PRINTED' THEN CURRENT_TIMESTAMP ELSE printed_at END,
                last_error=?
            WHERE id=?""",
            (status, status, last_error, print_id),
        )
        payload = {
            "event": "CASH_PRINT_DELIVERY_STATUS",
            "original_operation_id": original_operation_id,
            "status": status,
            "gateway_reference": gateway_reference,
            "error": last_error,
        }
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
                new_uuid(),
                actor_user_id,
                branch_id,
                entity_id,
                document_type,
                output_format,
                printer_id,
                copies,
                status,
                original_print_id,
                None,
                _json(payload),
                filename,
            ),
        )
