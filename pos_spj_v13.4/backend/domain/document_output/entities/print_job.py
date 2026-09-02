"""PrintJob — SET-11 (§24). Created for every print, never printed
directly from UI (§26/§70: "no imprimir directo desde UI").

Status machine::

    PENDING ──start_rendering()──► RENDERING ──mark_ready()──► READY ──start_printing()──► PRINTING ──mark_printed()──► PRINTED (terminal)
      │                                │                          │                             │
      │                                └──────fail(reason)────────┴─────────fail(reason)─────────┘
      │                                                            │
      └──────────────────────cancel()─────────────────────────────┘
                                                                    ▼
                                                                 FAILED ──retry()──► PENDING (retry_count += 1)
                                                                        └─move_to_dead_letter()─► DEAD_LETTER (terminal)

`source_module`/`source_document_id` are opaque references to whatever
created the job (a sale, a transfer, ...) — this entity never resolves
or validates them against another bounded context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.document_output.enums import PrintJobPriority, PrintJobStatus
from backend.domain.document_output.exceptions import (
    DocumentInvalidValueError,
    DocumentReprintNotAllowedError,
    PrintJobTransitionNotAllowedError,
)
from backend.shared.ids import new_uuid, validate_uuidv7

_CANCELLABLE = {PrintJobStatus.PENDING, PrintJobStatus.RENDERING, PrintJobStatus.READY}
_FAILABLE = {PrintJobStatus.RENDERING, PrintJobStatus.PRINTING}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class PrintJob:
    id: str
    document_type: str
    source_module: str
    source_document_id: str
    template_version_id: str
    requested_by_user_id: str
    copies: int = 1
    priority: PrintJobPriority = PrintJobPriority.NORMAL
    print_route_id: str | None = None
    printer_device_id: str | None = None
    status: PrintJobStatus = PrintJobStatus.PENDING
    requested_at: str = field(default_factory=_utcnow)
    rendered_at: str | None = None
    printed_at: str | None = None
    failure_reason: str | None = None
    retry_count: int = 0
    reprint_of_job_id: str | None = None
    reprint_reason: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, document_type: str, source_module: str, source_document_id: str,
        template_version_id: str, requested_by_user_id: str, copies: int = 1,
        priority: PrintJobPriority = PrintJobPriority.NORMAL, print_route_id: str | None = None,
        printer_device_id: str | None = None,
    ) -> "PrintJob":
        if not document_type.strip():
            raise DocumentInvalidValueError("document_type es obligatorio")
        if not source_module.strip():
            raise DocumentInvalidValueError("source_module es obligatorio")
        if not requested_by_user_id:
            raise DocumentInvalidValueError("requested_by_user_id es obligatorio")
        if isinstance(copies, bool) or not isinstance(copies, int) or copies < 1:
            raise DocumentInvalidValueError(f"copies debe ser un entero >= 1, recibido {copies!r}")
        return cls(
            id=new_uuid(), document_type=document_type.strip().upper(), source_module=source_module.strip(),
            source_document_id=validate_uuidv7(source_document_id),
            template_version_id=validate_uuidv7(template_version_id),
            requested_by_user_id=requested_by_user_id, copies=copies, priority=priority,
            print_route_id=print_route_id, printer_device_id=printer_device_id,
        )

    def create_reprint(self, *, requested_by_user_id: str, reason: str) -> "PrintJob":
        """§33: a reprint keeps the same participation/document — it's a
        new job, not a mutation of this one, and it always carries a
        reason."""
        if not reason.strip():
            raise DocumentReprintNotAllowedError("La reimpresión requiere un motivo")
        return PrintJob(
            id=new_uuid(), document_type=self.document_type, source_module=self.source_module,
            source_document_id=self.source_document_id, template_version_id=self.template_version_id,
            requested_by_user_id=requested_by_user_id, copies=self.copies, priority=self.priority,
            print_route_id=self.print_route_id, printer_device_id=self.printer_device_id,
            reprint_of_job_id=self.id, reprint_reason=reason.strip(),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # lifecycle ---------------------------------------------------------------
    def assign_route(self, *, print_route_id: str, printer_device_id: str) -> None:
        self.print_route_id = print_route_id
        self.printer_device_id = validate_uuidv7(printer_device_id)
        self._touch()

    def start_rendering(self) -> None:
        if self.status is not PrintJobStatus.PENDING:
            raise PrintJobTransitionNotAllowedError(f"No se puede renderizar desde {self.status.value}")
        self.status = PrintJobStatus.RENDERING
        self._touch()

    def mark_ready(self) -> None:
        if self.status is not PrintJobStatus.RENDERING:
            raise PrintJobTransitionNotAllowedError(f"No se puede marcar listo desde {self.status.value}")
        self.status = PrintJobStatus.READY
        self.rendered_at = _utcnow()
        self._touch()

    def start_printing(self) -> None:
        if self.status is not PrintJobStatus.READY:
            raise PrintJobTransitionNotAllowedError(f"No se puede imprimir desde {self.status.value}")
        if not self.printer_device_id:
            raise PrintJobTransitionNotAllowedError("No se puede imprimir sin printer_device_id asignado")
        self.status = PrintJobStatus.PRINTING
        self._touch()

    def mark_printed(self) -> None:
        if self.status is not PrintJobStatus.PRINTING:
            raise PrintJobTransitionNotAllowedError(f"No se puede marcar impreso desde {self.status.value}")
        self.status = PrintJobStatus.PRINTED
        self.printed_at = _utcnow()
        self._touch()

    def fail(self, reason: str) -> None:
        if self.status not in _FAILABLE:
            raise PrintJobTransitionNotAllowedError(f"No se puede fallar desde {self.status.value}")
        if not reason.strip():
            raise DocumentInvalidValueError("fail() requiere un motivo")
        self.status = PrintJobStatus.FAILED
        self.failure_reason = reason.strip()
        self._touch()

    def cancel(self) -> None:
        if self.status not in _CANCELLABLE:
            raise PrintJobTransitionNotAllowedError(f"No se puede cancelar desde {self.status.value}")
        self.status = PrintJobStatus.CANCELLED
        self._touch()

    def retry(self) -> None:
        if self.status is not PrintJobStatus.FAILED:
            raise PrintJobTransitionNotAllowedError(f"No se puede reintentar desde {self.status.value}")
        self.status = PrintJobStatus.PENDING
        self.retry_count += 1
        self.failure_reason = None
        self._touch()

    def move_to_dead_letter(self) -> None:
        if self.status is not PrintJobStatus.FAILED:
            raise PrintJobTransitionNotAllowedError(
                f"No se puede mover a dead-letter desde {self.status.value}"
            )
        self.status = PrintJobStatus.DEAD_LETTER
        self._touch()
