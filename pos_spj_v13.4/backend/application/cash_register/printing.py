"""Canonical CASH-24 printing orchestration for cash register documents.

This module owns authorization, idempotency, queue submission, reprint rules and
audit recording. It does not talk to UI widgets, database drivers, printer
drivers or schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.shared.ids import new_uuid, validate_uuidv7


class CashPrintDocumentType(str, Enum):
    X_CUT = "X_CUT"
    Z_CUT = "Z_CUT"
    MOVEMENT_RECEIPT = "MOVEMENT_RECEIPT"
    SAFE_DROP = "SAFE_DROP"
    HANDOVER = "HANDOVER"
    REFUND = "REFUND"


class CashPrintFormat(str, Enum):
    HTML = "HTML"
    ESC_POS = "ESC_POS"


@dataclass(frozen=True, slots=True)
class CashPrintDocument:
    document_type: CashPrintDocumentType
    entity_id: str
    branch_id: str
    reference: str
    title: str
    fields: tuple[tuple[str, str], ...]
    lines: tuple[tuple[str, ...], ...] = ()
    totals: tuple[tuple[str, str], ...] = ()
    barcode_value: str | None = None
    qr_value: str | None = None
    final: bool = False

    def __post_init__(self) -> None:
        validate_uuidv7(self.entity_id)
        validate_uuidv7(self.branch_id)
        if not self.reference or not self.title:
            raise ValueError("Cash print document requires reference and title")


@dataclass(frozen=True, slots=True)
class CashPrintArtifact:
    content: bytes
    media_type: str
    filename: str
    format: CashPrintFormat

    def __post_init__(self) -> None:
        if not self.content or not self.media_type or not self.filename:
            raise ValueError("Cash print artifact requires content, media_type and filename")


@dataclass(frozen=True, slots=True)
class CashPrintJob:
    print_id: str
    operation_id: str
    printer_id: str
    artifact: CashPrintArtifact
    copies: int
    document_type: CashPrintDocumentType
    entity_id: str
    branch_id: str
    original_print_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.print_id, self.operation_id, self.entity_id, self.branch_id):
            validate_uuidv7(value)
        if not self.printer_id:
            raise ValueError("Cash print job requires printer_id")
        if self.copies < 1 or self.copies > 10:
            raise ValueError("Cash print copies must be between 1 and 10")


@dataclass(frozen=True, slots=True)
class PrintCashDocumentCommand:
    operation_id: str
    actor_user_id: str
    document: CashPrintDocument
    printer_id: str
    output_format: CashPrintFormat = CashPrintFormat.HTML
    copies: int = 1
    original_print_id: str | None = None
    reprint_reason: str | None = None

    def __post_init__(self) -> None:
        validate_uuidv7(self.operation_id)
        validate_uuidv7(self.actor_user_id)
        if not self.printer_id:
            raise ValueError("Print command requires printer_id")
        if self.copies < 1 or self.copies > 10:
            raise ValueError("Cash print copies must be between 1 and 10")
        if self.original_print_id and not (self.reprint_reason or "").strip():
            raise ValueError("A cash reprint requires a reason")


class CashDocumentRenderer(Protocol):
    def render(self, document: CashPrintDocument) -> CashPrintArtifact: ...


class CashPrintQueue(Protocol):
    def enqueue(self, job: CashPrintJob) -> None: ...


class CashPrintAuditRepository(Protocol):
    def print_id_for_operation(self, operation_id: str) -> str | None: ...
    def original_exists(self, print_id: str, entity_id: str,
                        document_type: CashPrintDocumentType) -> bool: ...
    def record(self, *, print_id: str, command: PrintCashDocumentCommand,
               artifact: CashPrintArtifact, status: str,
               event_payload: dict[str, object]) -> None: ...


class InMemoryCashPrintQueue:
    """Deterministic queue adapter for unit tests and local composition."""

    def __init__(self) -> None:
        self.jobs: list[CashPrintJob] = []

    def enqueue(self, job: CashPrintJob) -> None:
        self.jobs.append(job)


class InMemoryCashPrintAuditRepository:
    """In-memory audit repository that preserves idempotency and reprint checks."""

    def __init__(self) -> None:
        self.by_operation: dict[str, str] = {}
        self.records: list[dict[str, object]] = []

    def print_id_for_operation(self, operation_id: str) -> str | None:
        return self.by_operation.get(operation_id)

    def original_exists(self, print_id: str, entity_id: str,
                        document_type: CashPrintDocumentType) -> bool:
        return any(
            record["print_id"] == print_id
            and record["command"].document.entity_id == entity_id
            and record["command"].document.document_type == document_type
            and record["status"] == "QUEUED"
            for record in self.records
        )

    def record(self, *, print_id: str, command: PrintCashDocumentCommand,
               artifact: CashPrintArtifact, status: str,
               event_payload: dict[str, object]) -> None:
        self.records.append({
            "print_id": print_id,
            "command": command,
            "artifact": artifact,
            "status": status,
            "event_payload": event_payload,
        })
        self.by_operation[command.operation_id] = print_id


class PrintCashDocumentUseCase:
    def __init__(self, *, authorization: CashAuthorizationPolicy,
                 renderers: dict[CashPrintFormat, CashDocumentRenderer],
                 queue: CashPrintQueue,
                 audit: CashPrintAuditRepository) -> None:
        self._authorization = authorization
        self._renderers = renderers
        self._queue = queue
        self._audit = audit

    def execute(self, command: PrintCashDocumentCommand) -> str:
        existing_print_id = self._audit.print_id_for_operation(command.operation_id)
        if existing_print_id is not None:
            return existing_print_id
        self._authorization.require(
            user_id=command.actor_user_id,
            permission_code=(CashPermissions.REPRINT if command.original_print_id
                             else CashPermissions.PRINT),
            branch_id=command.document.branch_id,
        )
        if command.original_print_id and not self._audit.original_exists(
                command.original_print_id,
                command.document.entity_id,
                command.document.document_type):
            raise ValueError("Original cash print does not exist for this document")
        renderer = self._renderers.get(command.output_format)
        if renderer is None:
            raise ValueError("No renderer configured for cash document")
        artifact = renderer.render(command.document)
        print_id = new_uuid()
        event_payload = cash_event_payload(
            CashEvents.CASH_DOCUMENT_PRINTED,
            operation_id=command.operation_id,
            entity_id=print_id,
            branch_id=command.document.branch_id,
            user_id=command.actor_user_id,
            document_entity_id=command.document.entity_id,
            document_type=command.document.document_type.value,
            output_format=command.output_format.value,
            printer_id=command.printer_id,
            copies=command.copies,
            original_print_id=command.original_print_id,
            reprint=bool(command.original_print_id),
        )
        job = CashPrintJob(
            print_id=print_id,
            operation_id=command.operation_id,
            printer_id=command.printer_id,
            artifact=artifact,
            copies=command.copies,
            document_type=command.document.document_type,
            entity_id=command.document.entity_id,
            branch_id=command.document.branch_id,
            original_print_id=command.original_print_id,
            metadata={"reference": command.document.reference},
        )
        try:
            self._queue.enqueue(job)
        except Exception:
            self._audit.record(print_id=print_id, command=command, artifact=artifact,
                               status="FAILED", event_payload=event_payload)
            raise
        self._audit.record(print_id=print_id, command=command, artifact=artifact,
                           status="QUEUED", event_payload=event_payload)
        return print_id
